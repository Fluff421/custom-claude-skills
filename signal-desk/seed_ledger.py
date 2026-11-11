"""Seed upcoming Ledger Game rows from ESPN's schedule (NFL and FBS).

Nothing else creates weekly Game rows, so without this job ESPN Sync and the Pick Engine find 0 upcoming games.
This job only creates the row; ESPN Sync, Context and the Pick Engine fill everything else on their next runs.

Rules
  - Window: Central dates from today through SEED_DAYS (default 7) ahead; only games ESPN still lists as
    not started (status state "pre").
  - Scope: games where BOTH teams have an ESPN FPI value (NFL plus FBS). FCS opponents are skipped and listed,
    never guessed. If a league's FPI index cannot be read, nothing is seeded for that league.
  - Dedupe: a game is skipped if a Ledger Game row already has its ESPN Event ID, or has the same league,
    a date within one day and both teams (either orientation; a reversed non-neutral match is reported).
  - Fields written (and only these): Record Type, League, Date, Game, Home Team, Away Team.
    No Splash line, FPI, ESPN line, tier, unit or note is ever written here.
  - Names: NFL uses ESPN's full name ("Buffalo Bills"); NCAAF uses ESPN's school name ("Miami (OH)").
  - Safety: dry run unless SEED_LEDGER_LIVE=1. A live run that would create more than SEED_MAX_CREATE
    (default 120) rows writes nothing and exits with an error.
  - Cost: ESPN JSON is fetched directly; no WebScraping.AI call is ever made by this job.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.parse
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import espn_sync as es  # noqa: E402

CENTRAL = ZoneInfo("America/Chicago")
SCOREBOARDS = {
    "NFL": es.ESPN + "/nfl/scoreboard?limit=100&dates={d}",
    "NCAAF": es.ESPN + "/college-football/scoreboard?groups=80&limit=300&dates={d}",  # FBS
}
FIELDS = ("Record Type", "League", "Date", "Game", "Home Team", "Away Team")


def team_name(league: str, team: dict) -> str:
    if league == "NFL":
        return team.get("displayName") or team.get("location") or ""
    return team.get("location") or team.get("shortDisplayName") or team.get("displayName") or ""


def central_date(iso: str) -> dt.date | None:
    try:
        ts = dt.datetime.strptime(iso.replace("Z", ""), "%Y-%m-%dT%H:%M").replace(tzinfo=dt.timezone.utc)
    except (ValueError, AttributeError):
        try:
            ts = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None
    return ts.astimezone(CENTRAL).date()


def fetch_events(league: str, dates: list[dt.date], get=None) -> list[dict]:
    """One scoreboard request per date (ESPN returns nothing for multi-day ranges), deduped by event id."""
    get = get or (lambda url: es.parse_json(es.scrape(url, "")))  # key "" = direct only, never the scraper
    events, seen = [], set()
    for d in dates:
        try:
            payload = get(SCOREBOARDS[league].format(d=d.strftime("%Y%m%d")))
        except Exception as exc:  # noqa: BLE001
            es.warn(f"{league} scoreboard fetch failed for {d}: {exc}")
            continue
        for ev in payload.get("events", []):
            if ev.get("id") and ev["id"] not in seen:
                seen.add(ev["id"])
                events.append(ev)
    return events


def existing_index(rows: list[dict]) -> tuple[set[str], list[dict]]:
    ids = {str(r["fields"].get("ESPN Event ID")) for r in rows if r["fields"].get("ESPN Event ID")}
    return ids, rows


def find_existing(league: str, day: dt.date, home: dict, away: dict, neutral: bool, rows: list[dict]):
    """('straight'|'swapped', row) when a Ledger row already covers this game, else None."""
    hn, an = es.names_for(home), es.names_for(away)
    for r in rows:
        f = r["fields"]
        if f.get("League") != league or not f.get("Date"):
            continue
        try:
            rd = dt.date.fromisoformat(f["Date"][:10])
        except ValueError:
            continue
        if abs((rd - day).days) > 1:
            continue
        h, a = f.get("Home Team", ""), f.get("Away Team", "")
        if es.ledger_matches(h, hn) and es.ledger_matches(a, an):
            return "straight", r
        if es.ledger_matches(h, an) and es.ledger_matches(a, hn):
            return "swapped", r
    return None


def plan(league: str, events: list[dict], fpi_ids: dict, rows: list[dict], start: dt.date, end: dt.date):
    """Returns (creates, report) without touching the network."""
    ids, rows = existing_index(list(rows))   # copy: planned rows are added locally for in-run dedupe
    creates, report = [], {"existing": 0, "started": 0, "outside": 0, "no_fpi": [], "reversed": [], "bad": 0}
    for ev in events:
        c = es.competitors(ev)
        home, away = c["home"], c["away"]
        day = central_date(ev.get("date", ""))
        if not home or not away or day is None:
            report["bad"] += 1
            continue
        if not (start <= day <= end):
            report["outside"] += 1
            continue
        state = (((ev.get("status") or {}).get("type") or {}).get("state")
                 or (((c["comp"].get("status") or {}).get("type") or {}).get("state")))
        if state != "pre":
            report["started"] += 1
            continue
        hname, aname = team_name(league, home), team_name(league, away)
        game = f"{aname} @ {hname}"
        if str(ev["id"]) in ids:
            report["existing"] += 1
            continue
        hit = find_existing(league, day, home, away, bool(c["comp"].get("neutralSite")), rows)
        if hit:
            report["existing"] += 1
            if hit[0] == "swapped" and not c["comp"].get("neutralSite"):
                report["reversed"].append(f"{game} {day} vs Ledger {hit[1]['fields'].get('Game')}")
            continue
        if str(home.get("id")) not in fpi_ids or str(away.get("id")) not in fpi_ids:
            report["no_fpi"].append(f"{game} {day}")
            continue
        creates.append({"fields": {"Record Type": "Game", "League": league, "Date": day.isoformat(),
                                   "Game": game, "Home Team": hname, "Away Team": aname}})
        rows.append({"fields": {"League": league, "Date": day.isoformat(), "Home Team": hname, "Away Team": aname}})
        ids.add(str(ev["id"]))
    return creates, report


def at_create(base: str, table: str, token: str, creates: list[dict]) -> int:
    n = 0
    for i in range(0, len(creates), 10):
        es.http_get(f"https://api.airtable.com/v0/{base}/{table}", es.at_headers(token), "POST",
                    {"records": creates[i:i + 10], "typecast": True})
        n += len(creates[i:i + 10])
    return n


def at_rows(base: str, table: str, token: str, since: dt.date) -> list[dict]:
    formula = f"AND({{Record Type}}='Game',IS_AFTER({{Date}},'{(since - dt.timedelta(days=2)).isoformat()}'))"
    out, offset = [], None
    while True:
        url = f"https://api.airtable.com/v0/{base}/{table}?pageSize=100&filterByFormula=" + urllib.parse.quote(formula)
        if offset:
            url += "&offset=" + urllib.parse.quote(offset, safe="")
        page = json.loads(es.http_get(url, es.at_headers(token)))
        out.extend(page.get("records", []))
        offset = page.get("offset")
        if not offset:
            return out


def main() -> None:
    token = os.environ.get("AIRTABLE_TOKEN", "").strip()
    base = os.environ.get("AIRTABLE_BASE_ID", "").strip()
    table = os.environ.get("LEDGER_TABLE_ID", "").strip() or es.LEDGER_DEFAULT
    live = os.environ.get("SEED_LEDGER_LIVE", "0").strip() == "1"
    days = int(os.environ.get("SEED_DAYS", "7") or 7)
    cap = int(os.environ.get("SEED_MAX_CREATE", "120") or 120)
    if not (token and base):
        raise SystemExit("ERROR: AIRTABLE_TOKEN and AIRTABLE_BASE_ID must be set.")
    today = dt.datetime.now(CENTRAL).date()
    end = today + dt.timedelta(days=days)
    rows = at_rows(base, table, token, today)
    query = [today + dt.timedelta(days=i) for i in range(days + 2)]  # +1 day for late kickoffs past UTC midnight
    all_creates, lines = [], []
    for league in ("NFL", "NCAAF"):
        fpi_ids = es.load_fpi_index(league, "")
        if not fpi_ids:
            lines.append(f"{league}: FPI index unavailable; nothing seeded for this league")
            continue
        events = fetch_events(league, query)
        creates, rep = plan(league, events, fpi_ids, rows, today, end)
        all_creates.extend(creates)
        lines.append(f"{league}: {len(events)} ESPN events, {len(creates)} to create, {rep['existing']} already in Ledger, "
                     f"{rep['started']} started/final, {rep['outside']} outside window, {len(rep['no_fpi'])} skipped (no FPI)")
        lines += [f"  create: {c['fields']['Date']} {c['fields']['Game']}" for c in creates]
        lines += [f"  skipped, no FPI: {x}" for x in rep["no_fpi"]]
        lines += [f"  WARNING reversed orientation, review: {x}" for x in rep["reversed"]]
    mode = "LIVE" if live else "DRY RUN"
    head = [f"Mode: {mode}", f"Window: {today} to {end} (Central)", f"Ledger Game rows read: {len(rows)}",
            f"Rows to create: {len(all_creates)} (cap {cap})",
            f"ESPN fetches: {es.DIRECT_STATS['direct']} direct, {es.DIRECT_STATS['scraper']} via scraper"]
    created = 0
    if live and len(all_creates) > cap:
        print("\n".join(head + lines))
        raise SystemExit(f"ERROR: {len(all_creates)} rows exceeds SEED_MAX_CREATE={cap}; nothing written.")
    if live and all_creates:
        created = at_create(base, table, token, all_creates)
    head.append(f"Rows created: {created}")
    out = head + lines + [f"WARN: {w}" for w in es.WARNINGS]
    print("\n".join(out))
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("## Seed Ledger\n\n" + "\n".join(f"- {x}" for x in out) + "\n")


if __name__ == "__main__":
    main()
