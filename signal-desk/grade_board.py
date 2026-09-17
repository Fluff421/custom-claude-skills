#!/usr/bin/env python3
"""Write ESPN final scores into Airtable BIM Weekly Board."""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request

ESPN_NFL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
ESPN_CFB = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?groups=80&limit=300"
ALIASES = {
    "MISS": {"MISS", "OLE MISS", "OM", "REBELS"},
    "TA&M": {"TA&M", "TAMU", "TAAM"},
    "M-OH": {"M-OH", "MIAOH", "MIAMI OH"},
    "WSH": {"WSH", "WAS"},
    "LV": {"LV", "LVRA"},
}


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "bim-grade-board/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def airtable_get(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def airtable_patch(url: str, token: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method="PATCH",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def norm(abbr: str) -> str:
    return re.sub(r"[^A-Z0-9&]", "", (abbr or "").upper())


def same_team(a: str, b: str) -> bool:
    na, nb = norm(a), norm(b)
    if na == nb:
        return True
    for group in ALIASES.values():
        nset = {norm(x) for x in group}
        if na in nset and nb in nset:
            return True
    return False


def parse_board_game(label: str) -> tuple[str, str] | None:
    parts = [p.strip() for p in (label or "").split("@")]
    if len(parts) != 2:
        return None
    return parts[0], parts[1]


def espn_finals(url: str) -> list[dict]:
    payload = get_json(url)
    out = []
    for event in payload.get("events", []):
        status = (event.get("status") or {}).get("type") or {}
        if not status.get("completed"):
            continue
        comps = event.get("competitions") or []
        if not comps:
            continue
        teams = {}
        for c in comps[0].get("competitors", []):
            home_away = c.get("homeAway")
            team = c.get("team") or {}
            teams[home_away] = {
                "abbr": team.get("abbreviation") or "",
                "score": c.get("score") or "0",
            }
        if "home" not in teams or "away" not in teams:
            continue
        away, home = teams["away"], teams["home"]
        out.append(
            {
                "away": away["abbr"],
                "home": home["abbr"],
                "result": f"{away['abbr']} {away['score']}-{home['score']} {home['abbr']}",
            }
        )
    return out


def list_open_records(base_id: str, table_id: str, token: str) -> list[dict]:
    records = []
    offset = None
    formula = urllib.parse.quote("NOT({Status}='Graded')")
    while True:
        url = f"https://api.airtable.com/v0/{base_id}/{table_id}?filterByFormula={formula}&pageSize=100"
        if offset:
            url += f"&offset={offset}"
        page = airtable_get(url, token)
        records.extend(page.get("records", []))
        offset = page.get("offset")
        if not offset:
            break
    return records


def main() -> None:
    token = os.environ["AIRTABLE_TOKEN"]
    base_id = os.environ.get("AIRTABLE_BASE_ID", "app1AdnkDQjzvr5l7")
    table_id = os.environ.get("AIRTABLE_TABLE_ID", "tblZ2Z7WSZ5awbQQX")
    finals = espn_finals(ESPN_NFL) + espn_finals(ESPN_CFB)
    updated = 0
    for rec in list_open_records(base_id, table_id, token):
        fields = rec.get("fields") or {}
        parsed = parse_board_game(fields.get("Game", ""))
        if not parsed:
            continue
        away, home = parsed
        match = next(
            (
                g
                for g in finals
                if same_team(away, g["away"]) and same_team(home, g["home"])
            ),
            None,
        )
        if not match:
            continue
        note = (fields.get("CLV note") or "").rstrip()
        if "Auto-graded" not in note:
            note = (note + " Auto-graded from ESPN.").strip()
        airtable_patch(
            f"https://api.airtable.com/v0/{base_id}/{table_id}/{rec['id']}",
            token,
            {"fields": {"Result": match["result"], "Status": "Graded", "CLV note": note}, "typecast": True},
        )
        updated += 1
        print(f"graded {fields.get('Game')} -> {match['result']}")
    print(f"updated {updated} records from {len(finals)} ESPN finals")


if __name__ == "__main__":
    main()
