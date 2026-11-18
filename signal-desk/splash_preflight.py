#!/usr/bin/env python3
"""Owner-side preflight for Splash File 1 / File 2 JSON. Read-only, no network.

Usage:
  python signal-desk/splash_preflight.py <dump.json> [--now 2026-11-16T22:30:00Z]
                                          [--ledger ledger_games.json] [--json]

The import workflow (splash_import.py) stops at the FIRST error. This script
lists EVERY problem it can find before anything is committed, so one
extraction can be fixed in one pass. It never edits the dump.

Levels:
  ERROR  the importer will reject the file, or a field breaks the contract.
  CHECK  the importer may accept it, but the owner must confirm the fact
         (for example a college game dated on a Sunday).

--ledger takes a JSON list of Airtable Ledger Game records shaped like
{"_id", "League", "Date", "Home Team", "Away Team"} (read-only export).
With it, the script also runs the importer's own plan() check, which is the
same validation the server runs, minus writing.

Exit codes: 0 no ERROR, 1 at least one ERROR, 2 unreadable input.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import math
import pathlib
import re
import sys
from zoneinfo import ZoneInfo

LINES = "signal-desk.splash-lines.v1"
PICKS = "signal-desk.splash-picks.v1"
CT = ZoneInfo("America/Chicago")
CHAT_LIMIT = 40_000          # observed regular-Search message limit
CHAT_SAFE = 36_000           # leave room for nothing else in the message
LEAGUES = ("NFL", "NCAAF")
CENTRAL_RE = re.compile(r"\d{4}-\d\d-\d\d \d\d:\d\d")
DATE_RE = re.compile(r"\d{4}-\d\d-\d\d")
STAMP_RE = re.compile(r"(\d{4}-\d\d-\d\d) (\d\d:\d\d):\d\d (CST|CDT)")
CODE_RE = re.compile(r"SPL-([LPC])-(\d{8})-(\d{4})")


class Report:
    def __init__(self):
        self.items = []

    def error(self, where, msg):
        self.items.append(("ERROR", where, msg))

    def check(self, where, msg):
        self.items.append(("CHECK", where, msg))

    @property
    def errors(self):
        return [i for i in self.items if i[0] == "ERROR"]


def finite(v):
    return (not isinstance(v, bool) and isinstance(v, (int, float))
            and math.isfinite(float(v)))


def american(v):
    return finite(v) and abs(float(v)) >= 100


def central_label(day: dt.date) -> str:
    return dt.datetime.combine(day, dt.time(12), CT).tzname()


def check_clock(d, r, kind_letter, now):
    code = d.get("date_code")
    m = CODE_RE.fullmatch(code) if isinstance(code, str) else None
    if not m:
        r.error("date_code", "must match SPL-L|P|C-YYYYMMDD-HHMM")
    elif m[1] not in kind_letter:
        r.error("date_code", f"prefix SPL-{m[1]} does not fit this schema/page_type")
    utc = None
    try:
        raw = d["extracted_at_utc"]
        if not (isinstance(raw, str) and raw.endswith("Z")):
            raise ValueError
        utc = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (KeyError, ValueError, TypeError):
        r.error("extracted_at_utc", "must be ISO 8601 UTC ending in Z, e.g. 2026-11-16T19:56:00Z")
    s = STAMP_RE.fullmatch(d.get("extracted_at_central") or "")
    if not s:
        r.error("extracted_at_central", "must be 'YYYY-MM-DD HH:MM:SS CST' or '... CDT'")
    if utc and s:
        local = utc.astimezone(CT)
        if local.strftime("%Y-%m-%d %H:%M") != f"{s[1]} {s[2]}" or local.tzname() != s[3]:
            r.error("extracted_at_central",
                    f"is not the same instant as extracted_at_utc (expected {local:%Y-%m-%d %H:%M} {local.tzname()})")
        if m and (m[2] != local.strftime("%Y%m%d") or m[3] != local.strftime("%H%M")):
            r.error("date_code", f"must equal the Central extraction minute SPL-{m[1]}-{local:%Y%m%d-%H%M}")
    if utc and now:
        age = (now - utc).total_seconds() / 3600
        limit = 12 if d.get("page_type") == "pending" else 24
        if age < -5 / 60:
            r.error("extracted_at_utc", "is in the future")
        elif age > limit:
            r.error("extracted_at_utc", f"is {age:.1f} h old; importer limit is {limit} h. Make a new capture")
        elif age > 4:
            r.check("extracted_at_utc", f"is {age:.1f} h old; prices older than 4 h are shown as stale")
    return utc


def check_lists(d, r):
    w = d.get("warnings")
    if not (isinstance(w, list) and all(isinstance(x, str) for x in w)):
        r.error("warnings", "must be a JSON array of strings ([] when nothing is unresolved)")
    elif w:
        for x in w:
            r.error("warnings", f"blocks import until resolved: {x!r}")
    n = d.get("notes")
    if n is not None and not (isinstance(n, list) and all(isinstance(x, str) for x in n)):
        r.check("notes", "should be a JSON array of strings")


def check_kickoff(where, g, r, required):
    k, tz, day = g.get("kickoff_central"), g.get("kickoff_tz"), None
    if k in (None, ""):
        if required:
            r.error(where, "kickoff_central is required (YYYY-MM-DD HH:MM Central)")
    elif not (isinstance(k, str) and CENTRAL_RE.fullmatch(k)):
        r.error(where, f"kickoff_central {k!r} must be YYYY-MM-DD HH:MM")
    else:
        day = dt.date.fromisoformat(k[:10])
    gd = g.get("game_date_central")
    if gd not in (None, ""):
        if not (isinstance(gd, str) and DATE_RE.fullmatch(gd)):
            r.error(where, f"game_date_central {gd!r} must be YYYY-MM-DD")
        elif day and gd != day.isoformat():
            r.error(where, "game_date_central conflicts with kickoff_central")
        else:
            day = day or dt.date.fromisoformat(gd)
    if tz not in (None, "", "CST", "CDT"):
        r.error(where, f"kickoff_tz {tz!r} is not allowed; use CST, CDT or null. "
                       "Keep the source zone (EST, ET, PT) only inside kickoff_as_shown")
    elif tz and day and tz != central_label(day):
        r.error(where, f"kickoff_tz {tz} is wrong for {day}; use {central_label(day)}")
    elif tz and not k:
        r.check(where, "kickoff_tz is set but kickoff_central is null; use null for both")
    return day


def lint_lines(d, r):
    games = d.get("games")
    if not (isinstance(games, list) and games):
        r.error("games", "must be a non-empty array")
        return
    actual = collections.Counter(g.get("league") for g in games if isinstance(g, dict))
    gc = d.get("game_count")
    if not isinstance(gc, dict):
        r.error("game_count", f"must be an object like {{\"NFL\": {actual.get('NFL', 0)}, "
                              f"\"NCAAF\": {actual.get('NCAAF', 0)}}}, not {gc!r}. "
                              "Do not copy a page widget number here")
    else:
        bad = [k for k, v in gc.items() if k not in LEAGUES or type(v) is not int or v < 0]
        if bad:
            r.error("game_count", f"only NFL/NCAAF non-negative integers allowed; bad keys {bad}")
        elif {k: v for k, v in gc.items() if v} != {k: v for k, v in actual.items() if v}:
            r.error("game_count", f"says {gc} but the games array has {dict(actual)}")
    seen = {}
    for i, g in enumerate(games):
        w = f"games[{i}]"
        if not isinstance(g, dict):
            r.error(w, "must be an object")
            continue
        label = f"{w} {g.get('away_team')} at {g.get('home_team')}"
        if g.get("league") not in LEAGUES:
            r.error(label, "league must be NFL or NCAAF")
        for t in ("away_team", "home_team"):
            if not (isinstance(g.get(t), str) and g[t].strip()):
                r.error(label, f"{t} is required")
        if g.get("home_away_certain") is not True:
            r.error(label, "home_away_certain must be true (explicit 'A at B' or '@'); "
                           "false or missing is rejected")
        for f in ("source", "date_code"):
            if f in g and g[f] != d.get(f):
                r.error(label, f"per-game {f} differs from the parent")
        day = check_kickoff(label, g, r, required=True)
        if day and g.get("league") == "NCAAF" and day.weekday() == 6:
            r.check(label, "NCAAF game dated on a Sunday; confirm the date")
        a, h = g.get("away_spread"), g.get("home_spread")
        if not (finite(a) and finite(h)):
            r.error(label, "away_spread and home_spread must be numbers (PK = 0)")
        elif float(a) != -float(h):
            r.error(label, f"away_spread {a} must equal minus home_spread {h}")
        if not finite(g.get("total")):
            r.error(label, "total must be a number")
        for f in ("away_spread_price", "home_spread_price", "over_price", "under_price", "away_ml", "home_ml"):
            v = g.get(f)
            if v is not None and not american(v):
                r.error(label, f"{f} {v!r} must be American odds (|x| >= 100) or null")
        key = (g.get("league"), g.get("away_team"), g.get("home_team"))
        rev = (g.get("league"), g.get("home_team"), g.get("away_team"))
        if key in seen:
            r.error(label, f"duplicate of games[{seen[key]}]")
        elif rev in seen:
            r.error(label, f"reversed duplicate of games[{seen[rev]}]")
        seen[key] = i


def lint_picks(d, r):
    pt = d.get("page_type")
    if pt not in ("pending", "completed"):
        r.error("page_type", "must be pending or completed")
    m = CODE_RE.fullmatch(d.get("date_code") or "")
    if m and pt and m[1] != ("P" if pt == "pending" else "C"):
        r.error("date_code", "SPL-P is for pending pages, SPL-C for completed pages")
    tickets = d.get("tickets")
    if not (isinstance(tickets, list) and tickets):
        r.error("tickets", "must be a non-empty array")
        return
    if type(d.get("ticket_count")) is not int or d["ticket_count"] != len(tickets):
        r.error("ticket_count", f"must be the integer {len(tickets)} counted from tickets")
    ids = set()
    for i, t in enumerate(tickets):
        w = f"tickets[{i}]"
        tid = t.get("ticket_id")
        if not (isinstance(tid, str) and tid.strip()):
            r.error(w, "ticket_id is required")
        elif tid in ids:
            r.error(w, f"duplicate ticket_id {tid}")
        ids.add(tid)
        typ, legs = t.get("ticket_type"), t.get("legs")
        if typ not in ("single", "parlay", "teaser"):
            r.error(w, f"ticket_type {typ!r} is not supported (single, parlay, teaser)")
        if not isinstance(legs, list) or not legs:
            r.error(w, "legs must be a non-empty array")
            continue
        if typ == "single" and len(legs) != 1:
            r.error(w, "single ticket must have exactly one leg")
        if typ in ("parlay", "teaser") and len(legs) < 2:
            r.error(w, f"{typ} needs at least two legs")
        stamps = {str(t.get(k)) for k in ("placed_as_shown", "settled_as_shown", "ticket_time_as_shown") if t.get(k)}
        basis = str(t.get("ticket_id_basis") or "")
        for j, leg in enumerate(legs):
            lw = f"{w}.legs[{j}] {leg.get('selection_as_shown') or leg.get('selection')}"
            if leg.get("league") not in LEAGUES:
                r.error(lw, "league must be NFL or NCAAF")
            for f in ("away_team", "home_team"):
                if not (isinstance(leg.get(f), str) and leg[f].strip()):
                    r.error(lw, f"{f} is required")
            if leg.get("home_away_certain") is False:
                r.error(lw, "uncertain orientation is rejected")
            day = check_kickoff(lw, leg, r, required=(pt == "pending"))
            if pt == "completed" and day is None:
                r.error(lw, "needs game_date_central (observed GAME date) or kickoff_central")
            if day and leg.get("league") == "NCAAF" and day.weekday() == 6:
                r.check(lw, "NCAAF game dated on a Sunday; the date may come from a settlement header")
            ks = leg.get("kickoff_as_shown")
            if ks and (ks in stamps or (basis and ks in basis)):
                r.error(lw, f"kickoff_as_shown {ks!r} is a ticket placement/settlement time, not a kickoff; use null")
            if ks and not leg.get("kickoff_central") and re.search(r"\d{1,2}:\d\d", str(ks)):
                r.check(lw, "kickoff_as_shown has a time but kickoff_central is null; confirm it is a real kickoff")
            mk = leg.get("market")
            sel = leg.get("selection")
            if mk not in ("spread", "total", "moneyline"):
                r.error(lw, f"market {mk!r} not supported")
            elif mk == "total":
                if not (isinstance(sel, str) and re.fullmatch(r"(Over|Under)(\s+\d+(\.\d+)?)?", sel)):
                    r.error(lw, "total selection must be Over or Under")
            elif sel not in (leg.get("away_team"), leg.get("home_team")):
                teams = [str(leg.get("away_team") or ""), str(leg.get("home_team") or "")]
                if isinstance(sel, str) and any(sel.lower() in x.lower() or x.lower() in sel.lower() for x in teams if x):
                    r.check(lw, "selection should copy the away_team or home_team label exactly")
                else:
                    r.error(lw, "spread/moneyline selection must name away_team or home_team")
            if mk == "moneyline":
                if typ == "teaser":
                    r.error(lw, "moneyline legs cannot be teased")
                if not american(leg.get("price")):
                    r.error(lw, "moneyline needs its actual American price; read it from the ticket detail")
            elif mk in ("spread", "total"):
                if not finite(leg.get("line")):
                    r.error(lw, "line must be a number (PK = 0)")
                if leg.get("price") is not None and not american(leg.get("price")):
                    r.error(lw, "price must be American odds or null")
                if typ == "teaser" and not finite(leg.get("teased_line")):
                    r.error(lw, "teaser leg needs the displayed final teased_line")
            if day and t.get("placed_at_central"):
                pa = str(t["placed_at_central"])[:10]
                if DATE_RE.fullmatch(pa) and pa > day.isoformat():
                    r.check(lw, f"placed_at_central {t['placed_at_central']} is after the game date {day}; "
                                "the page time may be a settlement time")


def server_plan(d, ledger_path, now, r):
    """Run the importer's own plan() read-only against an exported Ledger."""
    here = pathlib.Path(__file__).resolve().parent
    sys.path.insert(0, str(here))
    import splash_import as si
    import splash_lines as sl
    import repo_schedule as rs
    games = json.loads(pathlib.Path(ledger_path).read_text())
    lines = sl.read_csv(sl.LOG)
    last = max((x.get("captured_at_utc", "") for x in lines), default="")
    previous = [x for x in lines if x.get("captured_at_utc") == last]
    log = sl.read_csv(str(here / "intelligence/splash_picks_log.csv"))
    catalog = rs.RepositorySchedule(rs.load(here / "intelligence/splash_import/schedule.json"),
                                    games, si.matching, dump=d, digest="preflight")
    try:
        p = si.plan(d, games, previous, log, now or dt.datetime.now(dt.timezone.utc), {}, matcher=catalog.resolve)
        return {"server_check": "pass", "expected_rows": p["expected_rows"], "duplicate_tickets": len(p["duplicates"])}
    except Exception as exc:  # report, never raise
        r.error("server plan()", str(exc))
        return {"server_check": "reject", "first_error": str(exc)}


def lint(raw: bytes, now=None, ledger=None):
    r = Report()
    info = {"bytes": len(raw)}
    if raw.startswith(b"\xef\xbb\xbf"):
        r.error("file", "starts with a BOM; save as plain UTF-8")
    try:
        d = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        r.error("file", f"not valid JSON: {exc}. Copy only the JSON object, no fence or commentary")
        return r, info
    if not isinstance(d, dict):
        r.error("file", "top level must be one JSON object")
        return r, info
    if b"\n" in raw.rstrip(b"\n"):
        r.check("file", "is multi-line; new captures should be one compact line")
    if len(raw) > CHAT_LIMIT:
        r.check("file", f"{len(raw)} bytes exceeds the {CHAT_LIMIT}-character regular-Search message limit; "
                        "submit through Perplexity Computer as an attached file")
    elif len(raw) > CHAT_SAFE:
        r.check("file", f"{len(raw)} bytes is close to the {CHAT_LIMIT}-character chat limit")
    schema = d.get("schema")
    if schema == LINES:
        if d.get("source") != "Splash Sports Lines":
            r.error("source", "must be exactly 'Splash Sports Lines'")
        check_clock(d, r, "L", now)
        check_lists(d, r)
        lint_lines(d, r)
        info.update(kind="lines", games=len(d.get("games") or []),
                    by_league=dict(collections.Counter(g.get("league") for g in d.get("games") or [])))
    elif schema == PICKS:
        if d.get("source") != "Splash Sports Picks":
            r.error("source", "must be exactly 'Splash Sports Picks'")
        check_clock(d, r, "PC", now)
        check_lists(d, r)
        lint_picks(d, r)
        info.update(kind="picks", tickets=len(d.get("tickets") or []),
                    legs=sum(len(t.get("legs") or []) for t in d.get("tickets") or []))
    else:
        r.error("schema", f"{schema!r} is not {LINES} or {PICKS}")
        return r, info
    info["date_code"] = d.get("date_code")
    if ledger:
        info.update(server_plan(d, ledger, now, r))
    return r, info


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("path")
    ap.add_argument("--now", help="UTC instant for age checks, e.g. 2026-11-16T22:30:00Z")
    ap.add_argument("--ledger", help="read-only Ledger Game export (JSON list)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        raw = pathlib.Path(a.path).read_bytes()
    except OSError as exc:
        print(f"cannot read {a.path}: {exc}", file=sys.stderr)
        return 2
    now = dt.datetime.fromisoformat(a.now.replace("Z", "+00:00")) if a.now else dt.datetime.now(dt.timezone.utc)
    r, info = lint(raw, now, a.ledger)
    verdict = "FAIL" if r.errors else "PASS"
    if a.json:
        print(json.dumps({"verdict": verdict, **info,
                          "items": [{"level": l, "where": w, "message": m} for l, w, m in r.items]}, indent=2))
    else:
        print(f"{verdict}: {info}")
        for level, where, msg in r.items:
            print(f"{level:5} {where}: {msg}")
    return 1 if r.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
