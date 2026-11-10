#!/usr/bin/env python3
"""Compare the owner's Splash picks with the model, for every bet type, using the LOCKED line.

Input (env SPLASH_PICKS): one ticket per line (or separated by semicolons). Accepted forms:
  Spread       Alabama -7.5        Ohio State +3        Kansas State PK
  Total        Baltimore at Buffalo Over 45.5       Over 45.5 Baltimore @ Buffalo       Auburn vs Ole Miss u58
  Moneyline    Buffalo ML        Buffalo ML -180        Ole Miss moneyline +120
  Teaser       Teaser: Alabama -1.5, Over 45.5 Baltimore at Buffalo        (legs = BASE locked lines)
               Teaser: Alabama +4.5 teased, Under 51.5 Auburn at LSU teased   (a leg ending in 'teased' is the teased number)
  Parlay       Parlay: Alabama -7.5, Buffalo ML -180, Over 45.5 Baltimore at Buffalo
  Other        Other: Alabama alt -3.5 at +150     (logged and tracked, not graded)

What the line you paste means: Splash lines move all week. The ledger holds the early-week IMPORTED line; the line you
paste is the LOCKED line, the moment you made the pick, and it is the official number. A difference between the two is
line movement (or the 6-point adjustment on a teaser), never bad data. Picks are graded only against the locked line.
Picks for games that have started or finished are still logged and graded.

Read-only against Airtable. Splash data lives only in intelligence/splash_picks_log.csv (never written to Airtable).
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import close_grade as cg  # noqa: E402
import markets as mk  # noqa: E402

OUT = os.path.join(HERE, "intelligence")
LOG_COLS = ["logged_at", "locked_at", "ticket_id", "ticket_type", "ticket_legs", "market", "team", "side", "game", "record_id", "date", "league",
            "imported_line", "locked_line", "base_line", "teased_line", "price", "movement_for_you", "lead_days",
            "model_side_import", "model_tier_import", "model_side_lock", "model_tier_lock", "model_prob_lock", "model_edge_lock",
            "model_proj_lock", "side_changed", "matched", "status", "ticket_prob", "ticket_break_even", "text",
            "reference_origin", "ledger_record_id", "model_status"]

NUM = r"[+-]?\d+(?:\.\d+)?"
SPREAD = re.compile(rf"^(?P<team>[A-Za-z][A-Za-z0-9 .&'()\-]*?)\s+(?P<line>{NUM}|PK|pk|pick)(?:\s+\((?:spread)\))?\s*$")
ML = re.compile(rf"^(?P<team>[A-Za-z][A-Za-z0-9 .&'()\-]*?)\s+(?:ML|moneyline|money line)(?:\s+(?P<price>{NUM}))?\s*$", re.I)
SEP = r"(?:\s+at\s+|\s+@\s+|\s+vs\.?\s+|\s+v\s+)"
TOT_A = re.compile(rf"^(?P<a>.+?){SEP}(?P<b>.+?)\s+(?P<ou>over|under|o|u)\s*(?P<line>\d+(?:\.\d+)?)\s*$", re.I)
TOT_B = re.compile(rf"^(?P<ou>over|under|o|u)\s*(?P<line>\d+(?:\.\d+)?)\s+(?P<a>.+?){SEP}(?P<b>.+?)\s*$", re.I)
TICKET = re.compile(r"^(?P<kind>teaser|parlay|other)\s*[:\-]\s*(?P<body>.+)$", re.I)
TEASED = re.compile(r"\s*\(?\bteased\b\)?\s*$", re.I)
PREFIX = re.compile(r"^\s*(?:[-*\u2022]|\d+[.)])?\s*")


def parse_leg(text: str, teaser: bool = False) -> dict | None:
    t = PREFIX.sub("", text).strip()
    teased = False
    if teaser:
        m = TEASED.search(t)
        if m:
            teased, t = True, t[: m.start()].strip()
    m = TOT_A.match(t) or TOT_B.match(t)
    if m:
        ou = m.group("ou").lower()[0]
        return {"market": "total", "side": "over" if ou == "o" else "under", "away_or_a": m.group("a").strip(), "b": m.group("b").strip(),
                "line": float(m.group("line")), "price": None, "teased": teased}
    m = ML.match(t)
    if m:
        return {"market": "moneyline", "team": m.group("team").strip(), "line": 0.0, "price": float(m.group("price")) if m.group("price") else None, "teased": False}
    m = SPREAD.match(t)
    if m:
        ln = m.group("line")
        return {"market": "spread", "team": m.group("team").strip(), "line": 0.0 if ln.lower() in ("pk", "pick") else float(ln), "price": None, "teased": teased}
    return None


def parse_lines(text: str) -> tuple[list[dict], list[str]]:
    """Returns (tickets, unreadable). A ticket = {type: single|teaser|parlay|other, legs: [...], text}."""
    tickets, bad = [], []
    for raw in (text or "").replace(";", "\n").splitlines():
        if not raw.strip():
            continue
        body, kind = PREFIX.sub("", raw).strip(), "single"
        m = TICKET.match(body)
        if m:
            kind, body = m.group("kind").lower(), m.group("body").strip()
        if kind == "other":
            tickets.append({"type": "other", "legs": [{"market": "other", "text": body}], "text": raw.strip()})
            continue
        parts = [x.strip() for x in re.split(r",|\s\+\s", body) if x.strip()] if kind != "single" else [body]
        legs = [parse_leg(x, teaser=(kind == "teaser")) for x in parts]
        if not legs or any(l is None for l in legs) or (kind != "single" and len(legs) < 2):
            bad.append(raw.strip())
            continue
        tickets.append({"type": kind, "legs": legs, "text": raw.strip()})
    return tickets, bad


# ---------------------------------------------------------------- matching
def _today_distance(f: dict, today: dt.date) -> tuple[int, int]:
    try:
        d = dt.date.fromisoformat((f.get("Date") or "")[:10])
    except ValueError:
        return (999, 0)
    return (abs((d - today).days), 0 if d >= today else 1)


def _words(name: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (name or "").lower()))


def _side(team: str, f: dict, loose: bool) -> bool | None:
    h, a = f.get("Home Team", ""), f.get("Away Team", "")
    ish = cg.side_is_home(team, h, a)
    if ish is not None or not loose:
        return ish
    toks = _words(team)
    if not toks:
        return None
    hit = [(True, h), (False, a)]
    hit = [(side, name) for side, name in hit if toks <= _words(name)]
    return hit[0][0] if len(hit) == 1 else None


def match_team(team: str, games: list[dict], today: dt.date) -> tuple[dict, bool] | None:
    """Exact team match first; then a short name like 'Buffalo' or 'Bills' if it points at exactly one team."""
    for loose in (False, True):
        hit = _match_team(team, games, today, loose)
        if hit:
            return hit
    return None


def _match_team(team: str, games: list[dict], today: dt.date, loose: bool) -> tuple[dict, bool] | None:
    best = None
    names = set()
    for f in games:
        ish = _side(team, f, loose)
        if ish is None:
            continue
        names.add(f.get("Home Team") if ish else f.get("Away Team"))
        key = _today_distance(f, today)
        if best is None or key < best[0]:
            best = (key, f, ish)
    if loose and len(names) > 1:
        return None   # ambiguous short name (for example 'Kansas'): do not guess
    return None if best is None else (best[1], best[2])


def match_matchup(a: str, b: str, games: list[dict], today: dt.date) -> dict | None:
    best = None
    for f in games:
        h, w = f.get("Home Team", ""), f.get("Away Team", "")
        sa, sb = _side(a, f, True), _side(b, f, True)
        ok = sa is not None and sb is not None and sa != sb
        if ok and (best is None or _today_distance(f, today) < best[0]):
            best = (_today_distance(f, today), f)
    return None if best is None else best[1]


def imported_line(f: dict, market: str, side: str) -> float | None:
    """The early-week Splash line stored in the ledger, in the bet-side convention."""
    if market == "total":
        v = f.get("Over/Under Line")
        return None if v is None else float(v)
    v = f.get("Vegas Implied Home Margin")
    if v is None:
        return None
    return round(-float(v) if side == "home" else float(v), 2)


def movement_for_you(market: str, side: str, imported: float | None, locked: float) -> float | None:
    """Positive = the locked number was better for you than the imported one."""
    if imported is None or market == "moneyline":
        return None
    if market == "total":
        return round((imported - locked) if side == "over" else (locked - imported), 2)
    return round(locked - imported, 2)


# ---------------------------------------------------------------- model repricing at a line
def make_pricer(params_by_league: dict | None, counts: dict | None, now: str, factor_live: bool = False):
    """pricer(f, market, side, line, price) -> {side, tier, prob, edge, proj}: the model repriced AT the given line."""
    import picks as pk

    def pricer(f: dict, market: str, side: str, line: float | None, price: float | None) -> dict:
        if f.get("_model_status") == "unpriced":
            return {}
        league = f.get("League") or "NCAAF"
        p = mk.load_params(league, (params_by_league or {}).get(league), None)
        if market == "spread":
            hml = -line if side == "home" else line
            f2 = dict(f, **{"Vegas Implied Home Margin": hml})
            try:
                _, edge, tier, prob, _u = pk.evaluate(f2, (params_by_league or {}).get(league) or {}, counts or {}, now)
            except Exception:  # noqa: BLE001
                m = mk.model_margin(f)
                if m is None:
                    return {}
                edge = m - hml
                tier, prob = "n/a", 0.5
            return {"side": "home" if edge > 0 else "away", "tier": tier, "prob": round(prob, 4), "edge": round(edge, 2), "proj": mk.model_margin(f)}
        if market == "total":
            proj = mk.project_game(f, {"total": line}, p, factor_live)
            t = mk.total_pick(f, proj, None, p)
            if not t:
                return {}
            prob = t["prob"] if t["side"] == side else 1 - t["prob"]
            return {"side": t["side"], "tier": t["tier"], "prob": round(prob, 4), "edge": t["edge"], "proj": t["proj"]}
        if market == "moneyline":
            proj = mk.project_game(f, None, p, factor_live)
            ml = mk.moneyline_pick(f, proj, {"ml_home": price if side == "home" and price else None, "ml_away": price if side == "away" and price else None}
                                   if price else None, p)
            if not ml or proj.get("blend_margin") is None:
                return {}
            ph = mk.ND.cdf(proj["blend_margin"] / p["sigma_margin"])
            prob = ph if side == "home" else 1 - ph
            use_price = price if price else (mk.ml_prices(None, proj.get("line"), p["sigma_margin"])[0 if side == "home" else 1])
            return {"side": ml["side"], "tier": ml["tier"], "prob": round(prob, 4), "edge": round(prob - mk.be_prob(use_price), 4),
                    "proj": proj["blend_margin"]}
        return {}
    return pricer


def teaser_leg_prob(f: dict, leg: dict, base: float, teased: float, side: str, p: dict, factor_live: bool = False) -> float | None:
    """Model probability that a teased leg wins (key-number aware for spreads)."""
    if f.get("_model_status") == "unpriced" or base is None:
        return None
    if leg["market"] == "total":
        proj = mk.project_game(f, {"total": base}, p, factor_live)
        T = proj.get("proj_total")
        if T is None:
            return None
        return round(mk.ND.cdf((T - teased) / p["sigma_total"]) if side == "over" else mk.ND.cdf((teased - T) / p["sigma_total"]), 4)
    proj = mk.project_game(f, {"home_margin_line": -base if side == "home" else base}, p, factor_live)
    M = proj.get("blend_margin")
    if M is None:
        return None
    win, _ = mk.cover(M if side == "home" else -M, teased, p["sigma_margin"], f.get("League") or "NCAAF")
    return round(win, 4)


# ---------------------------------------------------------------- compare
def compare(tickets: list[dict], games: list[dict], now: str, pricer=None, today: dt.date | None = None,
            params_by_league: dict | None = None, factor_live: bool = False) -> tuple[list[dict], list[str]]:
    today = today or dt.date.fromisoformat(now[:10])
    rows, unmatched = [], []
    for ti, t in enumerate(tickets, 1):
        tid = f"{now[:16].replace(' ', 'T')}-{ti}"
        leg_rows = []
        for leg in t["legs"]:
            row = {"logged_at": now, "locked_at": now, "ticket_id": tid, "ticket_type": t["type"], "ticket_legs": len(t["legs"]),
                   "market": "teaser_leg" if t["type"] == "teaser" else leg["market"], "text": t["text"], "matched": "", "status": ""}
            if leg["market"] == "other":
                row.update({"status": "logged, not graded", "matched": "n/a", "game": leg["text"]})
                leg_rows.append(row)
                continue
            if leg["market"] == "total":
                f = match_matchup(leg["away_or_a"], leg["b"], games, today)
                ish = None
                team = f"{leg['away_or_a']} / {leg['b']}"
                side = leg["side"]
            else:
                hit = match_team(leg["team"], games, today)
                f, ish = (hit if hit else (None, None))
                team = leg["team"]
                side = None if ish is None else ("home" if ish else "away")
            if not f:
                row.update({"team": team, "side": leg.get("side", ""), "locked_line": leg["line"], "status": "no matching game", "matched": "unmatched"})
                unmatched.append(t["text"])
                leg_rows.append(row)
                continue
            raw = leg["line"]
            if t["type"] == "teaser":
                # base = the locked line before the 6-point adjustment
                if leg["teased"]:
                    teased = raw
                    if "observed_base_line" in leg:
                        base = leg["observed_base_line"]
                    elif leg["market"] == "spread":
                        base = raw - mk.TEASER_PTS
                    else:
                        base = raw + mk.TEASER_PTS if leg["side"] == "over" else raw - mk.TEASER_PTS
                else:
                    base = raw
                    if leg["market"] == "spread":
                        teased = raw + mk.TEASER_PTS
                    else:
                        teased = raw - mk.TEASER_PTS if leg["side"] == "over" else raw + mk.TEASER_PTS
                locked = teased
            else:
                base, teased, locked = None, None, raw
            side = side if leg["market"] != "total" else leg["side"]
            imp = imported_line(f, leg["market"] if leg["market"] != "moneyline" else "moneyline", side)
            cmp_line = base if base is not None else locked
            started = f.get("Home Score") is not None
            status = "final" if started else ("started or awaiting score" if (f.get("Date") or "")[:10] < today.isoformat() else "upcoming")
            try:
                lead = (dt.date.fromisoformat((f.get("Date") or "")[:10]) - dt.date.fromisoformat(now[:10])).days
            except ValueError:
                lead = ""
            row.update({"team": team, "side": side, "game": f.get("Game"), "record_id": f["_id"], "date": (f.get("Date") or "")[:10],
                        "league": f.get("League"), "imported_line": imp, "locked_line": locked, "base_line": base, "teased_line": teased,
                        "price": leg.get("price") if leg.get("price") is not None else "", "matched": "pending", "status": status, "lead_days": lead,
                        "movement_for_you": ("" if t["type"] == "teaser" and base is None
                                             else movement_for_you(leg["market"], side, imp, cmp_line))})
            row.update({"reference_origin": f.get("_reference_origin", "airtable"),
                        "ledger_record_id": f.get("_ledger_record_id") if f.get("_reference_origin") == "repository" else f["_id"],
                        "model_status": f.get("_model_status", "")})
            if f.get("_model_status") == "unpriced":
                row["matched"] = "unpriced"
            elif pricer and t["type"] != "teaser":
                at_lock = pricer(f, leg["market"], side, locked, leg.get("price")) or {}
                at_imp = pricer(f, leg["market"], side, imp, leg.get("price")) if imp is not None and leg["market"] != "moneyline" else {}
                row.update({"model_side_lock": at_lock.get("side", ""), "model_tier_lock": at_lock.get("tier", ""),
                            "model_prob_lock": at_lock.get("prob", ""), "model_edge_lock": at_lock.get("edge", ""),
                            "model_proj_lock": at_lock.get("proj", ""), "model_side_import": at_imp.get("side", ""),
                            "model_tier_import": at_imp.get("tier", "")})
                if at_lock.get("side"):
                    row["matched"] = "yes" if at_lock["side"] == side else "no"
                    if at_imp.get("side"):
                        row["side_changed"] = "yes" if at_imp["side"] != at_lock["side"] else "no"
            elif t["type"] == "teaser":
                p = mk.load_params(f.get("League") or "NCAAF", (params_by_league or {}).get(f.get("League")), None)
                pr = teaser_leg_prob(f, leg, base, teased, side, p, factor_live)
                row["model_prob_lock"] = "" if pr is None else pr
            leg_rows.append(row)
        # ticket-level pricing for teasers and parlays
        if t["type"] in ("teaser", "parlay"):
            probs = []
            for r, leg in zip(leg_rows, t["legs"]):
                pr = r.get("model_prob_lock")
                probs.append(None if pr in ("", None) else float(pr))
            if all(x is not None for x in probs) and all(r.get("record_id") for r in leg_rows):
                legs = [{"game_id": r["record_id"], "market_kind": "total" if r["side"] in ("over", "under") else ("moneyline" if r["market"] == "moneyline" else "spread"),
                         "side": r["side"], "prob": pr, "price": float(r["price"]) if r["price"] != "" else None, "pro_favorite": False}
                        for r, pr in zip(leg_rows, probs)]
                p0 = mk.load_params(leg_rows[0].get("league") or "NCAAF", None, None)
                c = mk.combo(legs, t["type"], p0)
                for r in leg_rows:
                    r["ticket_prob"], r["ticket_break_even"] = c["prob"], c["break_even_prob"]
        rows.extend(leg_rows)
    return rows, unmatched


# ---------------------------------------------------------------- grading
def grade_leg_row(r: dict, game: dict | None) -> str:
    """Win/Loss/Push/pending for one logged leg, against the LOCKED line only."""
    if not game or game.get("Home Score") is None or game.get("Away Score") is None or r.get("market") in ("other", ""):
        return "pending"
    try:
        line = float(r["locked_line"])
    except (KeyError, TypeError, ValueError):
        return "pending"
    market = "teaser_leg" if r["market"] == "teaser_leg" else r["market"]
    kind = "total" if r.get("side") in ("over", "under") else "spread"
    return mk.grade_leg(market, r["side"], line, game["Home Score"], game["Away Score"], kind)


def grade_log(rows: list[dict], by_id: dict) -> list[dict]:
    """Adds leg_result and ticket_result to each row (ticket_result groups rows with the same ticket_id)."""
    out = [dict(r, leg_result=grade_leg_row(r, by_id.get(r.get("record_id")))) for r in rows]
    tickets: dict[str, list[dict]] = {}
    for r in out:
        tickets.setdefault(r.get("ticket_id"), []).append(r)
    for legs in tickets.values():
        if legs[0].get("ticket_type") in ("teaser", "parlay"):
            res = mk.grade_combo([l["leg_result"] for l in legs]) if all(l.get("record_id") for l in legs) else "pending"
        else:
            res = legs[0]["leg_result"]
        for l in legs:
            l["ticket_result"] = res
    return out


def render(rows: list[dict], unmatched: list[str], bad: list[str], passes: list[dict], now: str) -> str:
    agree = sum(1 for r in rows if r.get("matched") == "yes")
    against = sum(1 for r in rows if r.get("matched") == "no")
    L = [f"# Your Splash picks vs the model, {now}", "",
         f"{len(rows)} legs compared at the line you locked: {agree} matched the model, {against} went against it. "
         "All model picks are paper picks. Line differences are normal line movement, not errors.", ""]
    from intelligence_report import md_table
    unpriced = sum(r.get("model_status") == "unpriced" for r in rows)
    if unpriced:
        L += [f"{unpriced} recorded legs are unpriced: repository game references exist, but verified model inputs do not. No probability or recommendation is supplied for them.", ""]
    def fmt(r):
        if r["market"] == "teaser_leg":
            return f"{r.get('team')} {float(r['base_line']):+g} -> {float(r['teased_line']):+g}" if r.get("base_line") not in ("", None) else r.get("team")
        if r["market"] == "total":
            return f"{str(r.get('side')).title()} {r.get('locked_line')}"
        if r["market"] == "moneyline":
            return f"{r.get('team')} ML {r.get('price') or ''}".strip()
        return f"{r.get('team')} {r.get('locked_line')}"
    L.append(md_table(["Game", "Type", "Your pick (locked)", "Early-week line", "Moved for you", "Model at lock", "Result"],
                      [[r.get("game"), r.get("ticket_type") + "/" + r["market"], fmt(r), r.get("imported_line", ""), r.get("movement_for_you", ""),
                        (f"{r.get('model_side_lock')} {r.get('model_tier_lock')}".strip() or ("prob " + str(r.get("model_prob_lock")) if r.get("model_prob_lock") else "")),
                        {"yes": "matched", "no": "went against", "pending": r.get("status", ""), "unpriced": "unpriced; " + r.get("status", ""), "unmatched": "no game found", "n/a": "tracked"}.get(r.get("matched"), "")]
                       for r in rows]))
    changed = [r for r in rows if r.get("side_changed") == "yes"]
    if changed:
        L += ["", "The model's side would change between the early-week line and your locked line:"] + [
            f"- {r['game']}: model {r.get('model_side_import')} at the early line, {r.get('model_side_lock')} at {r.get('locked_line')}" for r in changed]
    tix = {r["ticket_id"]: r for r in rows if r.get("ticket_prob") not in ("", None)}
    if tix:
        L += ["", "Combined tickets (model view): " + "; ".join(
            f"{r['ticket_type']} model {float(r['ticket_prob']) * 100:.1f}% vs break-even {float(r['ticket_break_even']) * 100:.1f}%" for r in tix.values())]
    if passes:
        L += ["", "Model suggested (Lean or better), you did not pick:"] + [f"- {f.get('Game')}: {f.get('Sharp-Sheet Tier')} {f.get('Recommended Side')}" for f in passes]
    if unmatched:
        L += ["", "Could not match to a game (kept in the log): " + "; ".join(unmatched)]
    if bad:
        L += ["", "Could not read these lines: " + "; ".join(bad) + ". Formats: `Team -3.5`, `A at B Over 45.5`, `Team ML -150`, `Teaser: leg, leg`, `Parlay: leg, leg`."]
    return "\n".join(L) + "\n"


def append_log(path, rows):
    """Regenerate the CSV header when adding provenance columns, retaining rows."""
    existing, extra = [], []
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            extra = [k for k in (reader.fieldnames or []) if k not in LOG_COLS]
            existing = list(reader)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=LOG_COLS + extra, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(existing + rows)


def main() -> None:
    import espn_sync as es
    import intelligence_report as ir
    import picks as pk
    token, base = os.environ.get("AIRTABLE_TOKEN", "").strip(), os.environ.get("AIRTABLE_BASE_ID", "").strip()
    if not (token and base):
        raise SystemExit("ERROR: AIRTABLE_TOKEN and AIRTABLE_BASE_ID must be set.")
    es.AIRTABLE_BASE = base
    tickets, bad = parse_lines(os.environ.get("SPLASH_PICKS", ""))
    if not tickets:
        raise SystemExit("No readable picks in SPLASH_PICKS.")
    today = ir.central_today()
    games = [r["fields"] | {"_id": r["id"]} for r in ir.fetch(base, token, ir.LEDGER, "{Record Type}='Game'")]
    import splash_lines as sl
    games = sl.with_repository_schedule(games)
    params = {r["fields"].get("League"): r["fields"] for r in ir.fetch(base, token, ir.PARAMS, "TRUE()")}
    try:
        pp, counts = pk.load_params(token), pk.graded_counts(base, token)
    except Exception as exc:  # noqa: BLE001
        es.warn(f"pick parameters unavailable, spreads repriced with defaults: {exc}")
        pp, counts = {}, {}
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%MZ")
    pricer = make_pricer(pp, counts, now, os.environ.get("FACTOR_MODE", "").lower() == "live")
    rows, unmatched = compare(tickets, games, now, pricer, today, params, os.environ.get("FACTOR_MODE", "").lower() == "live")
    picked = {r.get("record_id") for r in rows}
    passes = [f for f in games if (f.get("Date") or "")[:10] >= today.isoformat() and f.get("Home Score") is None
              and f.get("Sharp-Sheet Tier") in ("Lean", "Strong Play", "Max Play") and f["_id"] not in picked]
    text = render(rows, unmatched, bad, passes, now)
    os.makedirs(os.path.join(OUT, "splash_picks"), exist_ok=True)
    with open(os.path.join(OUT, "splash_picks", dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d-%H%M") + ".md"), "w", encoding="utf-8") as fh:
        fh.write(text)
    path = os.path.join(OUT, "splash_picks_log.csv")
    append_log(path, rows)
    print(text)


if __name__ == "__main__":
    main()
