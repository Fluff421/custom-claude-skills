#!/usr/bin/env python3
"""Write completed ESPN football scores to Airtable BIM Weekly Board via WebScraping.AI."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ESPN_NFL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
ESPN_CFB = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?groups=80&limit=300"
SCRAPER_URL = "https://api.webscraping.ai/html"
REQUIRED_ENV = ("AIRTABLE_TOKEN", "AIRTABLE_BASE_ID", "AIRTABLE_TABLE_ID", "WEBSCRAPING_AI_API_KEY")
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


def require_env() -> tuple[str, str, str, str]:
    missing = [key for key in REQUIRED_ENV if not os.environ.get(key, "").strip()]
    if missing:
        fail("Missing or empty GitHub Actions secret(s): " + ", ".join(missing))
    token = os.environ["AIRTABLE_TOKEN"].strip()
    base_id = os.environ["AIRTABLE_BASE_ID"].strip()
    table_id = os.environ["AIRTABLE_TABLE_ID"].strip()
    scraper_key = os.environ["WEBSCRAPING_AI_API_KEY"].strip()
    if not re.fullmatch(r"app[a-zA-Z0-9]+", base_id):
        fail("AIRTABLE_BASE_ID must start with 'app'.")
    if not re.fullmatch(r"tbl[a-zA-Z0-9]+", table_id):
        fail("AIRTABLE_TABLE_ID must start with 'tbl'.")
    return token, base_id, table_id, scraper_key


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


def scraper_json(target_url: str, api_key: str) -> dict:
    params = urllib.parse.urlencode({
        "api_key": api_key,
        "url": target_url,
        "js": "false",
        "proxy": "datacenter",
    })
    payload = request_json(f"{SCRAPER_URL}?{params}", {"Accept": "application/json"})
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            fail("WebScraping.AI returned text rather than ESPN JSON.")
    if not isinstance(payload, dict):
        fail("WebScraping.AI response did not contain a JSON object.")
    return payload


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


def espn_finals(url: str, api_key: str) -> list[dict]:
    payload = scraper_json(url, api_key)
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
    token, base_id, table_id, scraper_key = require_env()
    finals = espn_finals(ESPN_NFL, scraper_key) + espn_finals(ESPN_CFB, scraper_key)
    open_records = list_open_records(base_id, table_id, token)
    updated, unmatched = 0, []
    for record in open_records:
        fields = record.get("fields") or {}
        game = fields.get("Game", "")
        parsed = parse_game(game)
        if not parsed:
            unmatched.append(game or record["id"])
            continue
        away, home = parsed
        match = next((item for item in finals if same_team(away, item["away"]) and same_team(home, item["home"])), None)
        if not match:
            continue
        note = (fields.get("CLV note") or "").rstrip()
        if "Auto-graded from ESPN via WebScraping.AI." not in note:
            note = (note + " Auto-graded from ESPN via WebScraping.AI.").strip()
        update_record(base_id, table_id, record["id"], token, match["result"], note)
        print(f"graded {game} -> {match['result']}")
        updated += 1
    summary = [
        "Score source: ESPN via WebScraping.AI",
        f"ESPN finals found: {len(finals)}",
        f"Ungraded Airtable records scanned: {len(open_records)}",
        f"Records auto-graded: {updated}",
    ]
    if unmatched:
        summary.append("Invalid board labels skipped: " + ", ".join(unmatched[:20]))
    for line in summary:
        print(line)
    write_summary(summary)


if __name__ == "__main__":
    main()
