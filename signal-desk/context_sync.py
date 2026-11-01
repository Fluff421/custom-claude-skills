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
import situational as sit
import qb_nfl
import weather as wxm

LEDGER = "tbl3tFHFhvyNMpksE"
LOOKAHEAD_GAP = 8.0


def team_schedule(league: str, team_id: str, key: str, season: int | None = None) -> list[dict]:
    url = f"{es.ESPN}/{'nfl' if league == 'NFL' else 'college-football'}/teams/{team_id}/schedule"
    if season:
        url += f"?season={season}"
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
            "opp_id": str(((opp or {}).get("team") or {}).get("id") or ""),
            "home_away": side.get("homeAway"), "neutral": bool(comp.get("neutralSite")),
            "venue_state": ((((comp.get("venue") or {}).get("address")) or {}).get("state")),
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
    return {"last": last, "streak": streak, "next": nxt, "next_name": future[0]["opp_name"] if future else None,
            "next_id": future[0].get("opp_id") if future else None}

def home_state(games: list[dict]) -> str | None:
    """A team's home state = the most common venue state of its non-neutral home games."""
    from collections import Counter
    c = Counter(g["venue_state"] for g in games if g.get("home_away") == "home" and not g.get("neutral") and g.get("venue_state"))
    return c.most_common(1)[0][0] if c else None


def meetings_vs(opp_id: str, *schedules: list[dict]) -> list[dict]:
    """Completed games against one opponent across the given schedules, oldest first."""
    out = []
    for games in schedules:
        for g in games:
            if g["completed"] and g.get("opp_id") == opp_id and g["me"].get("score") is not None:
                my, op = _score(g["me"]), _score(g["opp"])
                out.append({"date": g["date"].strftime("%Y-%m-%d"), "won": my > op, "score": f"{my:g}-{op:g}"})
    return sorted(out, key=lambda m: m["date"])


GH_FEED = "https://api.github.com/repos/Fluff421/custom-claude-skills/contents/signal-desk/research/feed/{d}?ref=research/grok-feed"


def load_qb_feed(league: str) -> list[dict]:
    """Verified quarterback starter rows from the Grok research feed (newest date first). Never raises."""
    import csv
    import io
    hdr = {"User-Agent": "signal-desk", "Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        hdr["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    rows: list[dict] = []
    try:
        days = json.loads(es.http_get(GH_FEED.format(d=f"availability_{league.lower()}"), hdr))
        dirs = sorted((d["name"] for d in days if d.get("type") == "dir"), reverse=True)[:3]
        for d in dirs:
            listing = json.loads(es.http_get(GH_FEED.format(d=f"availability_{league.lower()}/{d}"), hdr))
            for fobj in listing:
                if fobj["name"] == "qb_starters.csv":
                    rows += list(csv.DictReader(io.StringIO(es.http_get(fobj["download_url"], {"User-Agent": "signal-desk"}))))
    except Exception as exc:  # noqa: BLE001
        es.warn(f"{league} QB feed not read: {exc}")
    return rows


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
        fpi = es.load_fpi_index(league, key)  # keyed by ESPN team id
        schedules: dict[str, list[dict]] = {}
        prev_sched: dict[str, list[dict]] = {}
        geo_cache: dict = {}
        fc_cache: dict = {}
        qb_rows = load_qb_feed(league)          # Grok-verified rows first, so they win over automatic ones
        nfl_inj = es.load_nfl_injuries(key) if league == "NFL" else {}
        qb_done: set[str] = set()
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
            new, sides, ids = {}, {}, {}
            comp0 = (ev.get("competitions") or [{}])[0]
            venue = comp0.get("venue") or {}
            vstate = (venue.get("address") or {}).get("state")
            neutral = bool(comp0.get("neutralSite"))
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
                ids[label] = tid
                if league == "NFL" and tid not in qb_done:
                    qb_done.add(tid)
                    try:
                        depth = es.parse_json(es.scrape(f"{es.ESPN}/nfl/teams/{tid}/depthcharts", key))
                        tname = (team or {}).get("displayName", "")
                        qb_rows.append(qb_nfl.team_row(tname, label.lower(), depth, nfl_inj.get(es.norm(tname), []),
                                                       es.norm, now.strftime("%Y-%m-%d")))
                    except Exception as exc:  # noqa: BLE001
                        es.warn(f"NFL QB depth chart for {(team or {}).get('displayName')} failed: {exc}")
            # rest days, travel, revenge, weather (situational context; priors scaled by the learning loop)
            try:
                for label in ("Home", "Away"):
                    if label in ids:
                        d = sit.rest_days(schedules[ids[label]], kickoff)
                        if d is not None:
                            new[f"{label} Rest Days"] = d
                tr = {}
                for label in ("Home", "Away"):
                    if label in ids:
                        hs = home_state(schedules[ids[label]])
                        tr[label] = sit.travel(hs, vstate) if (label == "Away" or neutral) else {"mi": 0, "tz": 0}
                if tr.get("Away") or tr.get("Home"):
                    new["Travel Note"] = sit.travel_note(tr.get("Away"), tr.get("Home"))
                flags = []
                if len(ids) == 2:
                    for label, other in (("Home", "Away"), ("Away", "Home")):
                        tid = ids[label]
                        if tid not in prev_sched:
                            prev_sched[tid] = team_schedule(league, tid, key, season=(kickoff or now).year - 1)
                        why = sit.revenge_flag(meetings_vs(ids[other], prev_sched[tid], schedules[tid]))
                        if why:
                            flags.append(f"{label} revenge ({why})")
                new["Revenge Note"] = "; ".join(flags) if flags else "none"
                wn = wxm.forecast_note((venue.get("address") or {}).get("city", ""), vstate or "", kickoff, now,
                                       bool(venue.get("indoor")), lambda u: es.parse_json(es.http_get(u, {"User-Agent": "signal-desk"})),
                                       geo_cache, fc_cache)
                if not wn:  # beyond the forecast window or lookup failed: keep ESPN's plain note (no severity, so no effect)
                    wn = sit.weather_note(ev.get("weather") or comp0.get("weather"), venue)
                    wn = (wn + " | no severity") if wn else ""
                if wn:
                    new["Weather Note"] = wn
            except Exception as exc:  # noqa: BLE001
                es.warn(f"{f.get('Game')}: situational context skipped: {exc}")
            qn = sit.qb_note(qb_rows, f.get("Home Team", ""), f.get("Away Team", ""), es.norm)
            if qn:
                new["QB Starter Note"] = qn
            # look-ahead: next opponent much stronger than today's opponent
            notes = []
            for label, opp_fpi_field, opp_side in (("Home", "Away FPI", "Away"), ("Away", "Home FPI", "Home")):
                s, cur = sides.get(label), f.get(opp_fpi_field)
                if not (s and s.get("next_name") and cur is not None and fpi):
                    continue
                nxt_fpi = fpi.get(s.get("next_id") or "")
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
