#!/usr/bin/env python3
"""Write completed ESPN football scores to Airtable BIM Weekly Board (direct ESPN JSON, no scraper)."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ESPN_NFL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
ESPN_CFB = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?groups=80&limit=300"
LOOKBACK_DAYS = 10  # board rows have no date we rely on, so search recent finals day by day
REQUIRED_ENV = ("AIRTABLE_TOKEN", "AIRTABLE_BASE_ID", "AIRTABLE_TABLE_ID")
ALIASES = {
    "MISS": {"MISS", "OLE MISS", "OM", "REBELS"},
    "TA&M": {"TA&M", "TAMU", "TAAM"},
    "M-OH": {"M-OH", "MIAOH", "MIAMI OH"},
    "WSH": {"WSH", "WAS"},
    "LV": {"LV", "LVRA"},
}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def require_env() -> tuple[str, str, str]:
    missing = [key for key in REQUIRED_ENV if not os.environ.get(key, "").strip()]
    if missing:
        fail("Missing or empty GitHub Actions secret(s): " + ", ".join(missing))
    token = os.environ["AIRTABLE_TOKEN"].strip()
    base_id = os.environ["AIRTABLE_BASE_ID"].strip()
    table_id = os.environ["AIRTABLE_TABLE_ID"].strip()
    if not re.fullmatch(r"app[a-zA-Z0-9]+", base_id):
        fail("AIRTABLE_BASE_ID must start with 'app'.")
    if not re.fullmatch(r"tbl[a-zA-Z0-9]+", table_id):
        fail("AIRTABLE_TABLE_ID must start with 'tbl'.")
    return token, base_id, table_id


def request_json(url: str, headers: dict | None = None, method: str = "GET", payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:1000]
        fail(f"HTTP {exc.code} from {urllib.parse.urlparse(url).netloc}: {body}")
    except urllib.error.URLError as exc:
        fail(f"Network error contacting {urllib.parse.urlparse(url).netloc}: {exc.reason}")
    except json.JSONDecodeError:
        fail(f"Non-JSON response from {urllib.parse.urlparse(url).netloc}")


def espn_json(url: str) -> dict:
    """Fetch an ESPN scoreboard directly (public JSON). Retries transient failures; fails loudly otherwise."""
    last = ""
    for attempt in range(3):
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "signal-desk-bim-grader"})
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                payload = json.loads(response.read().decode())
            if isinstance(payload, dict) and "events" in payload:
                return payload
            last = "response had no 'events' list"
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = f"{type(exc).__name__}: {exc}"
        time.sleep(2 * (attempt + 1))
    fail(f"ESPN scoreboard fetch failed for {urllib.parse.urlparse(url).path}: {last}")


def norm(value: str) -> str:
    return re.sub(r"[^A-Z0-9&]", "", (value or "").upper())


def same_team(left: str, right: str) -> bool:
    a, b = norm(left), norm(right)
    if a == b:
        return True
    return any(a in {norm(x) for x in group} and b in {norm(x) for x in group} for group in ALIASES.values())


def parse_game(value: str) -> tuple[str, str] | None:
    parts = [part.strip() for part in (value or "").split("@")]
    return (parts[0], parts[1]) if len(parts) == 2 and all(parts) else None


def lookback_dates(today: dt.date | None = None) -> list[str]:
    today = today or dt.datetime.now(dt.timezone(dt.timedelta(hours=-6))).date()  # US Central (approx.), fine for a 10-day window
    return [(today - dt.timedelta(days=n)).strftime("%Y%m%d") for n in range(LOOKBACK_DAYS)]


def espn_finals_window(url: str) -> list[dict]:
    """Finals for each of the last LOOKBACK_DAYS days (the bare scoreboard only shows ESPN's current window)."""
    sep = "&" if "?" in url else "?"
    finals: list[dict] = []
    for day in lookback_dates():
        finals.extend(espn_finals(f"{url}{sep}dates={day}"))
    return finals


def espn_finals(url: str) -> list[dict]:
    payload = espn_json(url)
    finals = []
    for event in payload.get("events", []):
        if not ((event.get("status") or {}).get("type") or {}).get("completed"):
            continue
        competitions = event.get("competitions") or []
        if not competitions:
            continue
        teams = {}
        for competitor in competitions[0].get("competitors", []):
            side = competitor.get("homeAway")
            team = competitor.get("team") or {}
            if side in {"home", "away"}:
                teams[side] = {"abbr": team.get("abbreviation", ""), "score": competitor.get("score", "0")}
        if {"home", "away"} <= teams.keys():
            finals.append({
                "away": teams["away"]["abbr"],
                "home": teams["home"]["abbr"],
                "result": f"{teams['away']['abbr']} {teams['away']['score']}-{teams['home']['score']} {teams['home']['abbr']}",
            })
    return finals


def airtable_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def list_open_records(base_id: str, table_id: str, token: str) -> list[dict]:
    records, offset = [], None
    formula = urllib.parse.quote("AND({Status}!='Graded',{Result}='')")
    table = urllib.parse.quote(table_id, safe="")
    while True:
        url = f"https://api.airtable.com/v0/{base_id}/{table}?filterByFormula={formula}&pageSize=100"
        if offset:
            url += "&offset=" + urllib.parse.quote(offset, safe="")
        page = request_json(url, airtable_headers(token))
        records.extend(page.get("records", []))
        offset = page.get("offset")
        if not offset:
            return records


def update_record(base_id: str, table_id: str, record_id: str, token: str, result: str, note: str) -> None:
    url = f"https://api.airtable.com/v0/{base_id}/{urllib.parse.quote(table_id, safe='')}/{record_id}"
    request_json(url, airtable_headers(token), "PATCH", {
        "fields": {"Result": result, "Status": "Graded", "CLV note": note},
        "typecast": True,
    })


def write_summary(lines: list[str]) -> None:
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("## BIM score grader\n\n" + "\n".join(f"- {line}" for line in lines) + "\n")


def main() -> None:
    token, base_id, table_id = require_env()
    finals = espn_finals_window(ESPN_NFL) + espn_finals_window(ESPN_CFB)
    open_records = list_open_records(base_id, table_id, token)
    updated, unmatched, ambiguous = 0, [], []
    for record in open_records:
        fields = record.get("fields") or {}
        game = fields.get("Game", "")
        parsed = parse_game(game)
        if not parsed:
            unmatched.append(game or record["id"])
            continue
        away, home = parsed
        matches = [item for item in finals if same_team(away, item["away"]) and same_team(home, item["home"])]
        if not matches:
            continue
        if len({item["result"] for item in matches}) > 1:  # same matchup played twice in the window
            ambiguous.append(game)
            continue
        match = matches[0]
        note = (fields.get("CLV note") or "").rstrip()
        if "Auto-graded from ESPN." not in note and "Auto-graded from ESPN via WebScraping.AI." not in note:
            note = (note + " Auto-graded from ESPN.").strip()
        update_record(base_id, table_id, record["id"], token, match["result"], note)
        print(f"graded {game} -> {match['result']}")
        updated += 1
    summary = [
        "Score source: ESPN scoreboard JSON (direct)",
        f"ESPN finals found (last {LOOKBACK_DAYS} days): {len(finals)}",
        f"Ungraded Airtable records scanned: {len(open_records)}",
        f"Records auto-graded: {updated}",
    ]
    if ambiguous:
        summary.append("Skipped (same matchup twice in the window, grade by hand): " + ", ".join(ambiguous[:20]))
    if unmatched:
        summary.append("Invalid board labels skipped: " + ", ".join(unmatched[:20]))
    for line in summary:
        print(line)
    write_summary(summary)


if __name__ == "__main__":
    main()
