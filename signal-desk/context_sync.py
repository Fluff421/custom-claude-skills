"""Phase 3a: momentum and look-ahead context for upcoming ledger games.

Daily. For each upcoming Game row, pulls each team's ESPN schedule and writes:
  Home/Away Last Result, Home/Away Streak, Home/Away Next Opponent, Look-Ahead Note.

Look-ahead rule: if a team's NEXT opponent is >= 8 FPI points stronger than today's
opponent, flag the possible look-ahead spot. Never touches picks or results.
Dry run by default (CONTEXT_SYNC_LIVE=1 to write).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import espn_sync as es

LEDGER = "tbl3tFHFhvyNMpksE"
LOOKAHEAD_GAP = 8.0


def team_schedule(league: str, team_id: str, key: str) -> list[dict]:
    url = f"{es.ESPN}/{'nfl' if league == 'NFL' else 'college-football'}/teams/{team_id}/schedule"
    payload = es.parse_json(es.scrape(url, key))
    out = []
    for ev in payload.get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        status = (ev.get("status") or comp.get("status") or {}).get("type") or {}
        side = None
        for c in comp.get("competitors", []):
            if str((c.get("team") or {}).get("id")) == str(team_id):
                side = c
        if side is None:
            continue
        opp = None
        for c in comp.get("competitors", []):
            if c is not side:
                opp = c
        try:
            when = dt.datetime.fromisoformat(ev["date"].replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001
            continue
        out.append({
            "date": when, "state": status.get("state"), "completed": status.get("completed", False),
            "me": side, "opp": opp, "opp_name": ((opp or {}).get("team") or {}).get("displayName", "?"),
        })
    return sorted(out, key=lambda g: g["date"])


def _score(side) -> float:
    """Score may be a number or an object like {value: 24, displayValue: '24'}."""
    s = (side or {}).get("score")
    if isinstance(s, dict):
        s = s.get("value")
    return float(s or 0)


def summarize(games: list[dict], after: dt.datetime | None = None) -> dict:
    """Last result, streak and next opponent from a team's schedule.

    `after` is the current game's kickoff: the 'next opponent' must be the game
    AFTER the one being played, never the current game itself."""
    done = [g for g in games if g["completed"] and g["me"].get("score") is not None]
    future = [g for g in games if g["state"] == "pre" and (after is None or g["date"] > after)]
    last, streak, nxt = None, None, None
    if done:
        g = done[-1]
        my, op = _score(g["me"]), _score(g["opp"])
        last = f"{'W' if my > op else ('L' if my < op else 'T')} {my:g}-{op:g} vs {g['opp_name']}"
        outcomes = "".join(("W" if _score(x["me"]) > _score(x["opp"]) else "L") for x in reversed(done))
        streak = outcomes[0] + str(len(outcomes) - len(outcomes.lstrip(outcomes[0])))
    if future:
        g = future[0]
        nxt = f"{g['opp_name']} ({g['date'].strftime('%a %m/%d')})"
    return {"last": last, "streak": streak, "next": nxt, "next_name": future[0]["opp_name"] if future else None}


def main() -> None:
    token = os.environ.get("AIRTABLE_TOKEN", "").strip()
    base = os.environ.get("AIRTABLE_BASE_ID", "").strip()
    es.AIRTABLE_BASE = base
    key = os.environ.get("WEBSCRAPING_AI_API_KEY", "").strip()
    live = os.environ.get("CONTEXT_SYNC_LIVE", "0").strip() == "1"
    if not (token and base and key):
        raise SystemExit("ERROR: AIRTABLE_TOKEN, AIRTABLE_BASE_ID and WEBSCRAPING_AI_API_KEY must be set.")

    rows = es.at_list(base, LEDGER, token)  # Date > yesterday, Record Type Game
    now = dt.datetime.now(dt.timezone.utc)
    report, updates = [], []
    by_league: dict[str, list[dict]] = {}
    for r in rows:
        by_league.setdefault(r["fields"].get("League", ""), []).append(r)

    for league, lrows in by_league.items():
        if league not in es.SCOREBOARDS:
            continue
        dates = sorted({r["fields"]["Date"][:10].replace("-", "") for r in lrows if r["fields"].get("Date")})
        try:
            events = es.espn_events(league, dates, key)
        except Exception as exc:  # noqa: BLE001
            es.warn(f"{league} scoreboard fetch failed: {exc}")
            continue
        fpi = es.load_fpi(league, key)
        schedules: dict[str, list[dict]] = {}
        for r in lrows:
            f = r["fields"]
            hit = es.match_event(r, events)
            if not hit:
                continue
            ev, c, swapped = hit
            home_t, away_t = (c["away"], c["home"]) if swapped else (c["home"], c["away"])
            try:
                kickoff = dt.datetime.fromisoformat(ev["date"].replace("Z", "+00:00"))
            except Exception:  # noqa: BLE001
                kickoff = None
            new, sides = {}, {}
            for label, team in (("Home", home_t), ("Away", away_t)):
                tid = str((team or {}).get("id") or "")
                if not tid:
                    continue
                if tid not in schedules:
                    schedules[tid] = team_schedule(league, tid, key)
                s = summarize(schedules[tid], after=kickoff)
                if s["last"]:
                    new[f"{label} Last Result"] = s["last"]
                if s["streak"]:
                    new[f"{label} Streak"] = s["streak"]
                if s["next"]:
                    new[f"{label} Next Opponent"] = s["next"]
                sides[label] = s
            # look-ahead: next opponent much stronger than today's opponent
            notes = []
            for label, opp_fpi_field, opp_side in (("Home", "Away FPI", "Away"), ("Away", "Home FPI", "Home")):
                s, cur = sides.get(label), f.get(opp_fpi_field)
                if not (s and s.get("next_name") and cur is not None and fpi):
                    continue
                nxt_fpi = es.fpi_for(s["next_name"], None, fpi)
                if nxt_fpi is None:
                    continue
                gap = nxt_fpi - float(cur)
                if gap >= LOOKAHEAD_GAP:
                    notes.append(f"{label} side may look ahead to {s['next_name']} (next-opp FPI {gap:+.1f} vs today).")
            if notes:
                new["Look-Ahead Note"] = " ".join(notes)
            if new:
                updates.append({"id": r["id"], "fields": new})
                report.append(f"{f.get('Game')}: " + ", ".join(new.keys()))

    mode = "LIVE" if live else "DRY RUN"
    if live and updates:
        es.at_patch(base, LEDGER, token, updates)
    lines = [f"Mode: {mode}", f"Rows updated: {len(updates)}"] + report[:60] + \
            [f"WARNING: {w}" for w in es.WARNINGS[:5]]
    print("\n".join(lines))
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("## Context sync\n\n" + "\n".join(f"- {x}" for x in lines) + "\n")


if __name__ == "__main__":
    main()
