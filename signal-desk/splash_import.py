#!/usr/bin/env python3
"""One owner-supplied JSON inbox. Read-only Airtable; no inferred lines or results.

Usage: python signal-desk/splash_import.py <inbox-file.json> [--check-only]
An inbox file is authorized by the owner's exact-file approval before its commit.
The workflow commits generated outputs and the input move in one data commit.
"""
from __future__ import annotations

import collections
import copy
import csv
import datetime as dt
import hashlib
import json
import math
import os
import pathlib
import re
import sys
from zoneinfo import ZoneInfo

import splash_compare as sc
import splash_lines as sl
import splash_pricecheck as sp
import repo_schedule as rs

LINES = "signal-desk.splash-lines.v1"
PICKS = "signal-desk.splash-picks.v1"
HERE = pathlib.Path(__file__).resolve().parent


class Rejected(ValueError):
    pass


def need(condition, message):
    if not condition:
        raise Rejected(message)


def number(value, label):
    need(not isinstance(value, bool), f"{label} must be a finite number")
    try:
        n = float(value)
    except (ValueError, TypeError):
        raise Rejected(f"{label} must be a finite number") from None
    need(math.isfinite(n), f"{label} must be a finite number")
    return n


def central(value):
    try:
        need(isinstance(value, str) and re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d", value),
             "a reliable Central game date/time is required; do not use settlement time as kickoff")
        return dt.datetime.strptime(value, "%Y-%m-%d %H:%M")
    except ValueError as exc:
        if isinstance(exc, Rejected):
            raise
        raise Rejected("invalid Central game date/time") from None


def matching(g, games):
    """Exact names first, then a short name only if unique in this league/date window."""
    if g.get("kickoff_central") not in (None, ""):
        kickoff = central(g["kickoff_central"])
        date = kickoff.date()
        need(g.get("game_date_central") in (None, "", date.isoformat()),
             "game_date_central conflicts with the observed kickoff date")
    else:
        value = g.get("game_date_central")
        need(isinstance(value, str) and re.fullmatch(r"\d{4}-\d\d-\d\d", value),
             "a reliable Central game date is required; do not infer it from placement or settlement")
        try:
            date = dt.date.fromisoformat(value)
        except ValueError:
            raise Rejected("invalid Central game date") from None
    label = g.get("kickoff_tz")
    need(label in (None, "", "America/Chicago",
                   dt.datetime.combine(date, dt.time(12), ZoneInfo("America/Chicago")).tzname()),
         "kickoff_tz conflicts with the Central date")
    league = g.get("league")
    need(league in ("NFL", "NCAAF"), "league must be NFL or NCAAF")
    window = [f for f in games if f.get("League") == league and f.get("Date")
              and abs((dt.date.fromisoformat(f["Date"][:10]) - date).days) <= 1]
    names = {f[k] for f in window for k in ("Home Team", "Away Team") if f.get(k)}

    def resolve(value):
        need(isinstance(value, str) and value.strip(), "both team names are required")
        exact = [n for n in names if sl.norm(n) == sl.norm(value)]
        if exact:
            return exact
        # Reuse the feed's existing, explicit team aliases. Do not invent
        # abbreviations or use partial overlap to bind a different opponent.
        # The league/date window, unique both-team match and orientation
        # checks below remain mandatory.
        import espn_sync as es
        aliases = [n for n in names
                   if es.ledger_matches(value, {es.norm(n)})
                   or es.ledger_matches(n, {es.norm(value)})]
        if aliases:
            return aliases
        tokens = sc._words(value)
        return [n for n in names if tokens and tokens <= sc._words(n)]

    away_choices, home_choices = resolve(g.get("away_team")), resolve(g.get("home_team"))
    hits = [f for f in window
            if ((f.get("Home Team") in home_choices and f.get("Away Team") in away_choices)
                or (f.get("Home Team") in away_choices and f.get("Away Team") in home_choices))]
    label = f"{g.get('away_team')} @ {g.get('home_team')} ({date})"
    # An unrelated partial-name collision is not a game match. This permits
    # File 1 to establish a genuinely absent BOTH-team pair without changing
    # the strict ambiguity/orientation policy for any viable existing game.
    need(hits, f"{label}: matches 0 Ledger rows; no rows created")
    for value, choices in ((g["away_team"], away_choices), (g["home_team"], home_choices)):
        need(len(choices) <= 1, f"{value}: ambiguous short team name in league/date window")
    need(len(hits) == 1, f"{label}: matches {len(hits)} Ledger rows; no rows created")
    f = hits[0]
    home = home_choices[0]
    need(f["Home Team"] == home, f"{label}: reversed orientation; review Neutral Site, do not flip")
    need(g.get("home_away_certain") is not False, f"{label}: uncertain orientation")
    return f


def reviewed_input(d, raw):
    """Apply only an explicit, checksum-bound owner review, never mutate the raw.

    A review is a separately approved repository file. Counts and resolutions
    remain auditable; observations, ticket dates, source IDs, odds and lines
    cannot be changed through this interface. Date-only matching is confined to
    completed picks and never supplies or fabricates a kickoff time.
    """
    code = d.get("date_code", "")
    need(isinstance(code, str) and re.fullmatch(r"SPL-[LPC]-\d{8}-\d{4}", code),
         "unsafe or missing date_code")
    path = HERE / "intelligence/splash_import/reviews" / (code + ".json")
    if not path.exists():
        return d, None
    review_raw = path.read_bytes()
    need(len(review_raw) <= 1_000_000, "owner review exceeds 1 MB")
    review = json.loads(review_raw)
    allowed = {"schema", "date_code", "input_sha256", "warning_resolutions",
               "count_policy", "completed_game_dates"}
    need(isinstance(review, dict) and set(review) <= allowed, "unsupported review changes")
    need(review.get("schema") == "signal-desk.splash-review.v1", "unsupported review schema")
    need(review.get("date_code") == code, "owner review date_code differs from source")
    need(review.get("input_sha256") == hashlib.sha256(raw).hexdigest(),
         "owner review checksum differs from original source bytes")
    out = copy.deepcopy(d)
    audit = copy.deepcopy(review)
    audit["review_sha256"] = hashlib.sha256(review_raw).hexdigest()
    audit["original_warnings"] = copy.deepcopy(d.get("warnings", []))
    audit["raw_metadata_preserved"] = True
    warnings = out.get("warnings", [])
    need(isinstance(warnings, list) and all(isinstance(w, str) for w in warnings),
         "warnings must be a list of strings")
    resolutions = review.get("warning_resolutions", [])
    need(isinstance(resolutions, list), "warning_resolutions must be a list")
    resolved = set()
    for item in resolutions:
        need(isinstance(item, dict) and set(item) == {"warning", "resolution"}
             and isinstance(item["resolution"], str) and item["resolution"].strip(),
             "each warning resolution needs exact warning text and a nonblank resolution")
        need(isinstance(item["warning"], str) and item["warning"] in warnings
             and item["warning"] not in resolved, "warning resolution is unknown or duplicated")
        resolved.add(item["warning"])
    out["warnings"] = [w for w in warnings if w not in resolved]
    if "count_policy" in review:
        need(d.get("schema") == LINES
             and review["count_policy"] == "owner_confirms_complete_games_array",
             "unsupported review count_policy; owner must confirm the captured array is complete")
        gl = d.get("games")
        need(isinstance(gl, list) and gl and all(isinstance(g, dict)
             and g.get("league") in ("NFL", "NCAAF") for g in gl), "invalid reviewed games array")
        audit["original_game_count"] = copy.deepcopy(d.get("game_count"))
        out["game_count"] = dict(collections.Counter(g["league"] for g in gl))
        audit["effective_game_count"] = copy.deepcopy(out["game_count"])
    if "completed_game_dates" in review:
        need(d.get("schema") == PICKS and d.get("page_type") == "completed",
             "completed_game_dates is only supported for completed picks")
        dates = review["completed_game_dates"]
        need(isinstance(dates, list), "completed_game_dates must be a list")
        seen = set()
        for item in dates:
            need(isinstance(item, dict)
                 and set(item) == {"ticket_id", "leg_index", "game_date_central"},
                 "unsupported completed_game_dates fields; kickoff times cannot be injected")
            tid, index, value = item["ticket_id"], item["leg_index"], item["game_date_central"]
            need(isinstance(tid, str) and type(index) is int and index >= 0,
                 "invalid completed_game_dates ticket identity")
            need((tid, index) not in seen, "duplicate completed_game_dates leg")
            seen.add((tid, index))
            tickets = [t for t in out.get("tickets", []) if t.get("ticket_id") == tid]
            need(len(tickets) == 1 and isinstance(tickets[0].get("legs"), list)
                 and index < len(tickets[0]["legs"]), "completed_game_dates references an unknown leg")
            leg = tickets[0]["legs"][index]
            need(leg.get("kickoff_central") in (None, "")
                 and leg.get("game_date_central") in (None, "", value),
                 "completed_game_dates cannot replace an observed kickoff or game date")
            need(isinstance(value, str) and re.fullmatch(r"\d{4}-\d\d-\d\d", value),
                 "invalid completed_game_dates date")
            try:
                dt.date.fromisoformat(value)
            except ValueError:
                raise Rejected("invalid completed_game_dates date") from None
            leg["game_date_central"] = value
    return out, audit


def signature(kind, rows):
    parts = sorted((r.get("record_id"), r.get("market"), r.get("side"),
                    str(number(r.get("locked_line"), "line")),
                    str(number(r["price"], "moneyline price"))
                    if r.get("market") == "moneyline" and r.get("price") not in (None, "") else "")
                   for r in rows)
    return hashlib.sha256(json.dumps([kind, parts], separators=(",", ":")).encode()).hexdigest()


def previous_signatures(log):
    grouped = collections.defaultdict(list)
    for r in log:
        grouped[(r.get("logged_at"), r.get("ticket_id"))].append(r)
    return {signature(rs[0]["ticket_type"], rs) for rs in grouped.values()
            if all(r.get("record_id") and r.get("market") in ("spread", "total", "moneyline", "teaser_leg")
                   and r.get("locked_line") not in (None, "") for r in rs)}


def finished_count_exception(d, games, previous):
    """Require per-league arithmetic and the SAME slate, not an unrelated old week."""
    declared = d["game_count"]
    actual = collections.Counter(g["league"] for g in d["games"])
    if any(declared.get(lg, 0) < actual.get(lg, 0) for lg in set(declared) | set(actual)):
        return False
    if not previous or dict(collections.Counter(r.get("league") for r in previous)) != declared:
        return False
    current = {matching(g, games)["_id"] for g in d["games"]}
    old = {r["record_id"] for r in previous}
    if not current <= old:
        return False
    byid = {g["_id"]: g for g in games}
    missing = [byid.get(rid) for rid in old - current]
    if not missing or any(not f or f.get("Home Score") is None or f.get("Away Score") is None for f in missing):
        return False
    counts = collections.Counter(f["League"] for f in missing)
    return all(declared.get(lg, 0) - actual.get(lg, 0) == counts.get(lg, 0)
               for lg in set(declared) | set(actual))


def plan(d, games, previous, log, now, prior_sources=None, matcher=None):
    resolve = matcher or matching
    need(isinstance(d, dict) and d.get("schema") in (LINES, PICKS), "unsupported schema")
    kind = "lines" if d["schema"] == LINES else "picks"
    need(d.get("source") == ("Splash Sports Lines" if kind == "lines" else "Splash Sports Picks"),
         "source must match the Splash schema exactly")
    code = d.get("date_code", "")
    need(isinstance(code, str) and re.fullmatch(r"SPL-[LPC]-\d{8}-\d{4}", code), "unsafe or missing date_code")
    need(code.startswith("SPL-L-" if kind == "lines" else ("SPL-P-", "SPL-C-")), "date_code/schema mismatch")
    try:
        stamp = dt.datetime.fromisoformat(d["extracted_at_utc"].replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError, AttributeError):
        raise Rejected("extracted_at_utc is missing or invalid") from None
    need(stamp.tzinfo is not None, "extracted_at_utc must include a timezone")
    age = (now - stamp).total_seconds() / 3600
    need(age >= -5 / 60, "extraction time is in the future")
    max_age = 12 if kind == "picks" and d.get("page_type") == "pending" else 24
    need(age <= max_age, f"dump exceeds {max_age} hours; request a fresh owner dump")
    need(not d.get("warnings"), "dump warnings require owner resolution before import")
    result = {"schema": d["schema"], "kind": kind, "date_code": code, "expected_rows": 0,
              "tickets": [], "duplicates": [], "matches": [], "age_hours": round(age, 2),
              "freshness_warning": "Older than 4 hours; verify current Splash quotes" if age > 4 else None}
    if kind == "lines":
        gl = d.get("games")
        need(isinstance(gl, list) and gl, "no games")
        declared = d.get("game_count")
        need(isinstance(declared, dict) and all(type(v) is int and v >= 0 for v in declared.values()),
             "game_count must contain nonnegative integer counts")
        actual = dict(collections.Counter(g.get("league") for g in gl))
        if {k: v for k, v in declared.items() if v} != actual:
            need(finished_count_exception(d, games, previous),
                 f"game_count says {declared} but actual entries are {actual}; no values patched")
        ids = set()
        for g in gl:
            central(g.get("kickoff_central"))
            need(g.get("source", d["source"]) == d["source"]
                 and g.get("date_code", code) == code, "game source/date_code conflicts with its dump")
            away, home = number(g.get("away_spread"), "away spread"), number(g.get("home_spread"), "home spread")
            need(away == -home, "away_spread must equal -home_spread")
            number(g.get("total"), "total")
            f = resolve(g, games)
            need(f["_id"] not in ids, "duplicate game in dump")
            ids.add(f["_id"])
            result["matches"].append(f["_id"])
        result["expected_rows"] = len(gl)
        return result

    tickets = d.get("tickets")
    need(isinstance(tickets, list) and tickets, "no tickets")
    need(type(d.get("ticket_count")) is int and d["ticket_count"] == len(tickets), "ticket_count mismatch")
    need(d.get("page_type") in ("pending", "completed"), "page_type must be pending or completed")
    known, source_ids = previous_signatures(log), set()
    for t in tickets:
        need(t.get("source", d["source"]) == d["source"]
             and t.get("date_code", code) == code, "ticket source/date_code conflicts with its dump")
        tid, typ, legs = t.get("ticket_id"), t.get("ticket_type"), t.get("legs")
        need(isinstance(tid, str) and tid.strip() and tid not in source_ids, "missing or duplicate source ticket_id")
        source_ids.add(tid)
        need(typ in ("single", "parlay", "teaser"), "unsupported ticket_type")
        need(isinstance(legs, list) and len(legs) >= (1 if typ == "single" else 2), "invalid ticket leg count")
        need(typ != "single" or len(legs) == 1, "single ticket must have one leg")
        text, expected, chosen = [], [], []
        for leg in legs:
            if d["page_type"] == "pending":
                central(leg.get("kickoff_central"))
            f = resolve(leg, games)
            result["matches"].append(f["_id"])
            market = leg.get("market")
            need(market in ("spread", "total", "moneyline"), "unsupported leg market")
            selection = leg.get("selection", "")
            teased = typ == "teaser"
            need(not teased or market != "moneyline", "moneyline teaser unsupported")
            if market == "total":
                m = re.fullmatch(r"(Over|Under)(?:\s+\d+(?:\.\d+)?)?", selection, re.I)
                need(m is not None, "total selection must be Over or Under")
                side = m[1].lower()
                prefix = f"{f['Away Team']} at {f['Home Team']} {side.title()}"
            else:
                selected = [n for n in (f["Away Team"], f["Home Team"]) if sl.norm(n) == sl.norm(selection)]
                if not selected:
                    tokens = sc._words(selection) if isinstance(selection, str) else set()
                    selected = [n for n in (f["Away Team"], f["Home Team"])
                                if tokens and tokens <= sc._words(n)]
                need(len(selected) == 1, "spread/moneyline selection must uniquely identify one matched team")
                side = "home" if selected[0] == f["Home Team"] else "away"
                prefix = selected[0]
            if market == "moneyline":
                price = number(leg.get("price"), "moneyline price")
                need(abs(price) >= 100, "invalid American moneyline price")
                line, piece = 0.0, f"{prefix} ML {price:+g}"
            else:
                if teased:
                    need(leg.get("teased_line") is not None, "explicit teased_line required; never infer a null teased line")
                line = number(leg.get("teased_line") if teased else leg.get("line"), "pick line")
                if teased and leg.get("base_line") is not None:
                    base = number(leg["base_line"], "base_line")
                    offset = -6 if side == "over" else 6
                    need(line == base + offset, "base_line and teased_line disagree")
                piece = f"{prefix} {line:g}" if market == "total" else f"{prefix} {line:+g}"
                if teased:
                    piece += " teased"
            text.append(piece)
            chosen.append(f)
            expected.append({"record_id": f["_id"], "market": "teaser_leg" if teased else market,
                             "side": side, "locked_line": line, "price": leg.get("price")})
        joined = ", ".join(text)
        joined = (typ.title() + ": " + joined) if typ != "single" else joined
        parsed, bad = sc.parse_lines(joined)
        need(len(parsed) == 1 and not bad and len(parsed[0]["legs"]) == len(legs), "converted picks are not losslessly parseable")
        for parsed_leg, leg in zip(parsed[0]["legs"], legs):
            parsed_leg["price"] = leg.get("price")
            if typ == "teaser":
                parsed_leg["observed_base_line"] = leg.get("base_line")
        key = signature(typ, expected)
        need(tid not in (prior_sources or {}) or prior_sources[tid] == key,
             "previously recorded source ticket_id has changed legs, lines, or moneyline price; owner review required")
        item = {"source_ticket_id": tid, "fingerprint": key, "text": joined, "ticket": parsed[0],
                "games": chosen, "expected": expected, "metadata": t}
        if key in known:
            result["duplicates"].append({"source_ticket_id": tid, "fingerprint": key, "reason": "same full ticket already recorded"})
        else:
            result["tickets"].append(item)
            result["expected_rows"] += len(legs)
            known.add(key)
    return result


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def reconcile(games, log):
    """Write a derived current-outcome view; preserve immutable pick-time log fields."""
    graded = sc.grade_log(log, {f["_id"]: f for f in games})
    return {"generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "note": "Ledger-derived outcomes at recorded Splash lines. Not a new owner result dump.",
            "sample_size_legs": len(graded),
            "leg_results": dict(collections.Counter(r["leg_result"] for r in graded)),
            "stale_capture_status_count": sum(r.get("status") != "final" and r["leg_result"] != "pending" for r in graded),
            "legs": graded}


def load_context():
    import intelligence_report as ir
    token, base = os.environ.get("AIRTABLE_TOKEN", ""), os.environ.get("AIRTABLE_BASE_ID", "")
    need(token and base, "Airtable read configuration is required")
    games = [r["fields"] | {"_id": r["id"]} for r in ir.fetch(base, token, ir.LEDGER, "{Record Type}='Game'")]
    log = sl.read_csv(str(HERE / "intelligence/splash_picks_log.csv"))
    return token, base, games, log


def reconcile_only():
    _, _, games, log = load_context()
    catalog = rs.RepositorySchedule(
        rs.load(HERE / "intelligence/splash_import/schedule.json"), games, matching)
    games = catalog.games()
    if catalog.state["games"]:
        save_json(HERE / "intelligence/splash_import/schedule.json", catalog.state)
    save_json(HERE / "intelligence/splash_import/reconciliation/latest.json", reconcile(games, log))


def execute(path, check_only=False, now=None):
    import intelligence_report as ir
    import picks as pk
    raw = path.read_bytes()
    need(len(raw) <= 1_000_000, "input exceeds 1 MB")
    original = json.loads(raw)
    need(isinstance(original, dict), "input must be a JSON object")
    d, review = reviewed_input(original, raw)
    token, base, games, log = load_context()
    lines = sl.read_csv(sl.LOG)
    last = max((r.get("captured_at_utc", "") for r in lines), default="")
    previous = [r for r in lines if r.get("captured_at_utc") == last]
    now = now or dt.datetime.now(dt.timezone.utc)
    digest = hashlib.sha256(raw).hexdigest()
    schedule_path = HERE / "intelligence/splash_import/schedule.json"
    catalog = rs.RepositorySchedule(rs.load(schedule_path), games, matching, dump=d, digest=digest)
    prior_sources = {}
    for prior in (HERE / "intelligence/splash_import/receipts").glob("*.json"):
        for source, fingerprint in json.loads(prior.read_text()).get("source_tickets", {}).items():
            need(source not in prior_sources or prior_sources[source] == fingerprint,
                 "receipt source ticket_id conflict; owner review required")
            prior_sources[source] = fingerprint
    p = plan(d, games, previous, log, now, prior_sources, matcher=catalog.resolve)
    games = catalog.games()
    p["reference_matches"] = catalog.match_details(p["matches"])
    code = p["date_code"]
    need(path.name == code + ".json", "filename must equal date_code.json")
    receipt_path = HERE / "intelligence/splash_import/receipts" / (code + ".json")
    if receipt_path.exists():
        old = json.loads(receipt_path.read_text())
        need(old.get("input_sha256") == digest, "date_code already exists with different content; submit a new extraction")
        need(old.get("status") == "accepted", "previous receipt is not accepted")
        need((old.get("owner_review") or {}).get("review_sha256")
             == (review or {}).get("review_sha256"),
             "accepted import owner review is immutable; no history or baseline rewrite")
        print(f"Already accepted {code}; no duplicate rows appended.")
        if not check_only:
            destination = path.parent.parent / "processed" / path.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            path.rename(destination)
        return
    print(f"Validated {code}: {p['expected_rows']} new rows, {len(p['duplicates'])} duplicate tickets")
    if check_only:
        return
    params = {r["fields"].get("League"): r["fields"] for r in ir.fetch(base, token, ir.PARAMS, "TRUE()")}
    pricer = sc.make_pricer(pk.load_params(token, base), pk.graded_counts(base, token),
                            now.strftime("%Y-%m-%d %H:%MZ"), os.environ.get("FACTOR_MODE") == "live")
    new_rows, files = [], {}
    files[schedule_path] = json.dumps(catalog.state, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if p["kind"] == "picks":
        for item in p["tickets"]:
            rows, unmatched = sc.compare([item["ticket"]], item["games"], now.strftime("%Y-%m-%d %H:%MZ"),
                                          pricer, ir.central_today(), params, os.environ.get("FACTOR_MODE") == "live")
            need(not unmatched and len(rows) == len(item["expected"]), "comparison did not match every leg")
            for r, expected in zip(rows, item["expected"]):
                need(all(str(r[k]) == str(expected[k]) for k in ("record_id", "market", "side")), "comparison attached a leg to the wrong game")
                need(float(r["locked_line"]) == expected["locked_line"], "comparison changed an official line")
                r["ticket_id"] = "splash-" + item["fingerprint"][:24]
            new_rows.extend(rows)
        need(len(new_rows) == p["expected_rows"], "row-count mismatch")
        if new_rows:
            import io
            buff = io.StringIO(newline="")
            writer = csv.DictWriter(buff, fieldnames=sc.LOG_COLS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(log + new_rows)
            files[HERE / "intelligence/splash_picks_log.csv"] = buff.getvalue()
        files[HERE / "intelligence/splash_picks" / (code + ".md")] = sc.render(new_rows, [], [], [], now.strftime("%Y-%m-%d %H:%MZ"))
        files[HERE / "intelligence/splash_picks" / (code + ".md")] += (
            "\nProcessing-time reconstruction, not proof of a saved pregame forecast. "
            "Owner stakes, quoted payout, and reported settlement remain in the raw input "
            "and receipt; the comparison's reference calculations are not an actual payout statement.\n")
        # Preserve the established full-name text representation without re-running
        # the legacy inbox workflow or leaving a second pending input.
        files[HERE / "intelligence/splash_picks/processed" / (code + ".txt")] = (
            "\n".join(item["text"] for item in p["tickets"]) + "\n")
    else:
        need(not any(r.get("snapshot_id") == code for r in lines), "snapshot exists without an import receipt; manual review required")
        latest = json.loads(pathlib.Path(sl.PICKS_LATEST).read_text()) if pathlib.Path(sl.PICKS_LATEST).exists() else {}
        matched_ids = set(p["matches"])
        matched_games = [f for f in games if f["_id"] in matched_ids]
        new_rows, unmatched, flags = sl.build_rows(d, matched_games, lines, sl.read_csv(sl.MARKET_LOG), latest)
        need(not unmatched and not flags and len(new_rows) == p["expected_rows"], "line generation did not match the validated batch")
        import io
        buff = io.StringIO(newline="")
        writer = csv.DictWriter(buff, fieldnames=sl.COLS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(lines + new_rows)
        files[pathlib.Path(sl.LOG)] = buff.getvalue()
        unpriced = [f for f in matched_games if f.get("_model_status") == "unpriced"]
        notes = [f"{len(unpriced)} repository-reference games are unpriced; no model forecast or independent schedule verification is implied."] if unpriced else []
        report = sl.render(d, new_rows, [], [], notes, sl.movement_learning(lines + new_rows, {f["_id"]: f for f in games}))
        files[pathlib.Path(sl.DIR) / (code + ".md")] = report
        files[pathlib.Path(sl.DIR) / "latest.md"] = report
        results = [sp.check_game(f, r, pricer, params, os.environ.get("FACTOR_MODE") == "live")
                   for r in new_rows for f in games if f["_id"] == r["record_id"]
                   and f.get("Home Score") is None and f.get("Date", "") >= ir.central_today().isoformat()]
        files[pathlib.Path(sp.DIR) / "latest.md"] = sp.render(results, p["age_hours"], now.strftime("%Y-%m-%d %H:%MZ"))
        files[pathlib.Path(sp.DIR) / "latest.json"] = json.dumps(
            {"generated_at": now.isoformat(), "snapshot_age_hours": p["age_hours"], "games": results}, indent=1)
    for target, text in files.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    raw_path = HERE / "intelligence" / ("splash_lines" if p["kind"] == "lines" else "splash_picks") / "raw" / (code + ".json")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(raw)
    receipt = {k: v for k, v in p.items() if k != "tickets"}
    receipt.update({"status": "accepted", "processed_at_utc": now.isoformat(), "input_sha256": digest,
                    "owner_review": review,
                    "actual_new_rows": len(new_rows), "airtable_writes": 0,
                    "assessment_note": "Processing-time reconstruction, not proof of a saved pregame forecast.",
                    "ticket_metadata": original.get("tickets", []),
                    "source_tickets": {item["source_ticket_id"]: item["fingerprint"]
                                       for item in p["tickets"] + p["duplicates"]},
                    "line_report": f"signal-desk/intelligence/splash_lines/{code}.md" if p["kind"] == "lines" else None,
                    "pick_report": f"signal-desk/intelligence/splash_picks/{code}.md" if p["kind"] == "picks" else None})
    save_json(receipt_path, receipt)
    save_json(HERE / "intelligence/splash_import/reconciliation/latest.json", reconcile(games, log + new_rows if p["kind"] == "picks" else log))
    destination = path.parent.parent / "processed" / path.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    path.rename(destination)
    print(f"Accepted {code}: {len(new_rows)} new rows. Airtable writes: 0.")


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["--reconcile"]:
            reconcile_only()
            raise SystemExit(0)
        need(len(sys.argv) in (2, 3), "supply exactly one inbox JSON filename")
        need(len(sys.argv) == 2 or sys.argv[2] == "--check-only", "the only optional argument is --check-only")
        path = pathlib.Path(sys.argv[1]).resolve()
        need(path.parent == HERE / "intelligence/splash_import/inbox" and path.suffix == ".json",
             "input must be a .json file directly in intelligence/splash_import/inbox")
        execute(path, "--check-only" in sys.argv[2:])
    except (Rejected, ValueError, TypeError, KeyError) as exc:
        print(f"REJECTED. No accepted receipt or data commit: {exc}", file=sys.stderr)
        raise SystemExit(1)
