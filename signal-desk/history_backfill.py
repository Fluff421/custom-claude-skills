#!/usr/bin/env python3
"""Backfill past seasons for walk-forward validation (read-only on ESPN, writes repo CSVs only).

For every completed NFL and FBS game in the requested seasons it records final score, the pre-game book's
closing spread and total (parsed exactly like the live system, via markets.parse_odds), the opening spread,
and ESPN's pre-game FPI game projection with its lastModified time, so the leakage audit can check it.

    python history_backfill.py 2022 2023 2024 2025      -> data/history/{nfl,ncaaf}_{season}.csv

Nothing here touches Airtable.
"""
from __future__ import annotations

import concurrent.futures as cf
import csv
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import markets as mk  # noqa: E402

OUT = os.path.join(HERE, "data", "history")
SITE = "https://site.api.espn.com/apis/site/v2/sports/football/{lg}/scoreboard?dates={season}&seasontype={st}&week={wk}&limit=400{grp}"
CORE = "https://sports.core.api.espn.com/v2/sports/football/leagues/{lg}/events/{eid}/competitions/{eid}/{what}"
LEAGUES = {"NFL": ("nfl", "", {2: range(1, 19), 3: range(1, 6)}),
           "NCAAF": ("college-football", "&groups=80", {2: range(1, 17), 3: range(1, 2)})}
COLS = ["league", "season", "season_type", "week", "event_id", "kickoff_utc", "home", "away", "neutral", "conference_game",
        "home_score", "away_score", "provider", "close_home_margin_line", "open_home_margin_line", "close_total",
        "ml_home", "ml_away", "fpi_home_win_pct", "predictor_last_modified"]


def get(url: str, tries: int = 4) -> dict | None:
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "signal-desk-history", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1.5 * (i + 1))
    return None


def games(league: str, season: int) -> list[dict]:
    slug, grp, weeks = LEAGUES[league]
    out, seen = [], set()
    for st, wks in weeks.items():
        for wk in wks:
            d = get(SITE.format(lg=slug, season=season, st=st, wk=wk, grp=grp)) or {}
            for e in d.get("events", []):
                c = (e.get("competitions") or [{}])[0]
                if e["id"] in seen or not (((e.get("status") or {}).get("type") or {}).get("completed")):
                    continue
                t = {x.get("homeAway"): x for x in c.get("competitors", [])}
                if {"home", "away"} - t.keys():
                    continue
                seen.add(e["id"])
                out.append({"league": league, "season": season, "season_type": st, "week": wk, "event_id": e["id"],
                            "kickoff_utc": e.get("date"), "home": t["home"]["team"].get("abbreviation"),
                            "away": t["away"]["team"].get("abbreviation"), "neutral": int(bool(c.get("neutralSite"))),
                            "conference_game": int(bool(c.get("conferenceCompetition"))),
                            "home_score": t["home"].get("score"), "away_score": t["away"].get("score")})
    return out


def enrich(g: dict) -> dict:
    slug = LEAGUES[g["league"]][0]
    o = get(CORE.format(lg=slug, eid=g["event_id"], what="odds"))
    if o:  # skip empty books (e.g. a blank Bet365 item listed first in 2022-23 NFL) before using the live parser
        o = {**o, "items": [i for i in (o.get("items") or []) if i.get("spread") is not None
                            and (i.get("homeTeamOdds") or {}).get("favorite") is not None]}
    p = mk.parse_odds(o) if o and o["items"] else None
    if p:
        g.update(provider=p.get("provider"), close_home_margin_line=p.get("home_margin_line"),
                 open_home_margin_line=p.get("open_margin_line"), close_total=p.get("total"),
                 ml_home=p.get("ml_home"), ml_away=p.get("ml_away"))
    pr = get(CORE.format(lg=slug, eid=g["event_id"], what="predictor"))
    if pr:
        st = {s.get("name"): s.get("value") for s in ((pr.get("homeTeam") or {}).get("statistics") or [])}
        g.update(fpi_home_win_pct=st.get("gameProjection"), predictor_last_modified=pr.get("lastModified"))
    return g


def main(seasons: list[int]) -> None:
    os.makedirs(OUT, exist_ok=True)
    for season in seasons:
        for league in LEAGUES:
            path = os.path.join(OUT, f"{league.lower()}_{season}.csv")
            if os.path.exists(path):
                print("exists, skipping", path)
                continue
            gs = games(league, season)
            with cf.ThreadPoolExecutor(12) as ex:
                rows = list(ex.map(enrich, gs))
            rows.sort(key=lambda r: (r["kickoff_utc"] or "", r["event_id"]))
            with open(path, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore")
                w.writeheader()
                w.writerows(rows)
            n_line = sum(1 for r in rows if r.get("close_home_margin_line") not in (None, ""))
            n_fpi = sum(1 for r in rows if r.get("fpi_home_win_pct") not in (None, ""))
            print(f"{league} {season}: {len(rows)} finals, {n_line} with closing line, {n_fpi} with FPI projection", flush=True)


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]] or [2022, 2023, 2024, 2025])
