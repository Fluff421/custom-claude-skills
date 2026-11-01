"""Situational context: rest days, travel, revenge, weather, and quarterback-starter notes.

Pure functions (no network, no Airtable). context_sync.py fills the ledger text fields from ESPN
and the Grok research feed; factors.py reads them back through the parsers here. All point values are
PRIOR ASSUMPTIONS (not measured) so the learning loop (factor_learning.py) has something to scale.
Weather is recorded only and never changes a number until CLV shows it helps.
"""
from __future__ import annotations

import datetime as dt
import math
import re

# --- priors (spread points; positive = helps that team). Unvalidated. -------------------------
REST_BYE_DAYS = 12
REST_SHORT_DAYS = 5
REST_BYE_PTS = {"NFL": 0.5, "NCAAF": 0.6}
REST_SHORT_PTS = {"NFL": 0.7, "NCAAF": 0.6}      # subtracted
TRAVEL_MI_STEPS = ((2000, 0.5), (1000, 0.3))     # (miles, pts lost)
TRAVEL_TZ_PTS = 0.2                               # extra when 2+ time zones crossed
REVENGE_PTS = {"NFL": 0.3, "NCAAF": 0.3}

# State centroids (lat, lon) and rough time-zone offset from Eastern (0 ET, 1 CT, 2 MT, 3 PT).
STATES = {
    "AL": (32.8, -86.8, 1), "AK": (64.0, -150.0, 4), "AZ": (34.3, -111.7, 2), "AR": (34.9, -92.4, 1),
    "CA": (37.2, -119.5, 3), "CO": (39.0, -105.5, 2), "CT": (41.6, -72.7, 0), "DE": (39.0, -75.5, 0),
    "DC": (38.9, -77.0, 0), "FL": (28.6, -82.4, 0), "GA": (32.7, -83.4, 0), "HI": (20.8, -156.3, 5),
    "ID": (44.4, -114.6, 2), "IL": (40.0, -89.2, 1), "IN": (39.9, -86.3, 0), "IA": (42.1, -93.5, 1),
    "KS": (38.5, -98.4, 1), "KY": (37.5, -85.3, 0), "LA": (31.1, -91.9, 1), "ME": (45.4, -69.2, 0),
    "MD": (39.0, -76.8, 0), "MA": (42.3, -71.8, 0), "MI": (44.3, -85.4, 0), "MN": (46.3, -94.3, 1),
    "MS": (32.7, -89.7, 1), "MO": (38.4, -92.5, 1), "MT": (47.0, -109.6, 2), "NE": (41.5, -99.8, 1),
    "NV": (39.3, -116.6, 3), "NH": (43.7, -71.6, 0), "NJ": (40.1, -74.7, 0), "NM": (34.4, -106.1, 2),
    "NY": (42.9, -75.5, 0), "NC": (35.6, -79.4, 0), "ND": (47.5, -100.5, 1), "OH": (40.3, -82.8, 0),
    "OK": (35.6, -97.5, 1), "OR": (43.9, -120.6, 3), "PA": (40.9, -77.8, 0), "RI": (41.7, -71.5, 0),
    "SC": (33.9, -80.9, 0), "SD": (44.4, -100.2, 1), "TN": (35.9, -86.4, 1), "TX": (31.5, -99.3, 1),
    "UT": (39.3, -111.7, 2), "VT": (44.1, -72.7, 0), "VA": (37.5, -78.8, 0), "WA": (47.4, -120.5, 3),
    "WV": (38.6, -80.6, 0), "WI": (44.6, -89.9, 1), "WY": (43.0, -107.5, 2),
}


def days_between(earlier: dt.datetime, later: dt.datetime) -> int:
    """Whole days between two kickoffs, by US Central calendar date (kickoffs near midnight UTC stay on the right day)."""
    off = dt.timedelta(hours=-6)
    return ((later + off).date() - (earlier + off).date()).days


def rest_days(games: list[dict], kickoff: dt.datetime | None) -> int | None:
    """Days since this team's previous COMPLETED game before `kickoff` (None before the first game)."""
    if kickoff is None:
        return None
    prev = [g for g in games if g.get("completed") and g["date"] < kickoff]
    return days_between(prev[-1]["date"], kickoff) if prev else None


def miles(a: str | None, b: str | None) -> float | None:
    if a not in STATES or b not in STATES:
        return None
    la1, lo1, _ = STATES[a]
    la2, lo2, _ = STATES[b]
    p1, p2 = math.radians(la1), math.radians(la2)
    d = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lo2 - lo1) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(d))


def travel(home_state: str | None, venue_state: str | None) -> dict | None:
    """Crude travel from a team's home state to the venue state (state centroids; same state = 0)."""
    m = miles(home_state, venue_state)
    if m is None:
        return None
    if home_state == venue_state:
        return {"mi": 0, "tz": 0}
    return {"mi": int(round(m, -1)), "tz": abs(STATES[home_state][2] - STATES[venue_state][2])}


def travel_note(away: dict | None, home: dict | None) -> str:
    def part(label, t):
        return f"{label} {t['mi']}mi/{t['tz']}tz" if t else f"{label} n/a"
    return f"{part('AWAY', away)} | {part('HOME', home)}"


_TRAVEL = re.compile(r"AWAY (\d+)mi/(\d+)tz \| HOME (\d+)mi/(\d+)tz")


def travel_penalty(mi: float, tz: float) -> float:
    pts = 0.0
    for lim, p in TRAVEL_MI_STEPS:
        if mi >= lim:
            pts = p
            break
    if tz >= 2:
        pts += TRAVEL_TZ_PTS
    return pts


def rest_value(days: int | None, league: str) -> float:
    if days is None:
        return 0.0
    if days >= REST_BYE_DAYS:
        return REST_BYE_PTS.get(league, 0.5)
    if days <= REST_SHORT_DAYS:
        return -REST_SHORT_PTS.get(league, 0.6)
    return 0.0


def situational_points(fields: dict, league: str) -> dict:
    """Home-favoring spread points from rest, travel and revenge, with a per-factor breakdown."""
    out = {"rest": 0.0, "travel": 0.0, "revenge": 0.0}
    h, a = fields.get("Home Rest Days"), fields.get("Away Rest Days")
    if h is not None or a is not None:
        out["rest"] = rest_value(h, league) - rest_value(a, league)
    m = _TRAVEL.search(fields.get("Travel Note") or "")
    if m:
        am, at, hm, ht = (float(x) for x in m.groups())
        out["travel"] = travel_penalty(am, at) - travel_penalty(hm, ht)
    note = fields.get("Revenge Note") or ""
    rp = REVENGE_PTS.get(league, 0.3)
    out["revenge"] = (rp if "Home revenge" in note else 0.0) - (rp if "Away revenge" in note else 0.0)
    return {k: round(v, 2) for k, v in out.items()}


def revenge_flag(meetings: list[dict]) -> str | None:
    """`meetings` = this team's completed games vs the SAME opponent, oldest first, each {'won': bool, 'date', 'score'}.
    Revenge = the team lost the most recent meeting."""
    if not meetings:
        return None
    last = meetings[-1]
    if last["won"]:
        return None
    return f"lost {last['date']} {last['score']}"


def weather_note(weather: dict | None, venue: dict | None) -> str:
    """Log-only. ESPN supplies this only for upcoming games."""
    indoor = (venue or {}).get("indoor")
    if indoor:
        return "indoor"
    if not weather:
        return ""
    bits = []
    if weather.get("temperature") is not None:
        bits.append(f"{weather['temperature']}F")
    if weather.get("conditionId"):
        bits.append(str(weather["conditionId"]))
    return ", ".join(bits)


# --- quarterback starter checks (Grok feed qb_starters.csv) -----------------------------------
QB_FRACTION = {"starter_out": 1.0, "starter_questionable": 0.25, "starter_playing": 0.0}
_QB = re.compile(r"(HOME|AWAY) QB (OUT|QUESTIONABLE|PLAYING) ")


def qb_note(rows: list[dict], home_name: str, away_name: str, norm) -> str:
    """Build the ledger note from verified feed rows for one game. Unverified/unknown rows are ignored."""
    parts = []
    for side, team in (("HOME", home_name), ("AWAY", away_name)):
        for r in rows:
            if norm(r.get("team", "")) != norm(team) or (r.get("verified") or "").strip().lower() != "verified":
                continue
            label = {"starter_out": "OUT", "starter_questionable": "QUESTIONABLE", "starter_playing": "PLAYING"}.get(
                (r.get("classification") or "").strip())
            if label:
                rep = f" -> {r['replacement']}" if r.get("replacement") else ""
                parts.append(f"{side} QB {label} {r.get('starter', '?')}{rep} [verified {r.get('source_date', '?')}]")
                break
    return " | ".join(parts)


def qb_fractions(note: str | None) -> dict:
    """{'home': 1.0, 'away': 0.0} for sides the feed spoke about (absent = no information)."""
    out = {}
    for side, label in _QB.findall(note or ""):
        out[side.lower()] = QB_FRACTION[{"OUT": "starter_out", "QUESTIONABLE": "starter_questionable", "PLAYING": "starter_playing"}[label]]
    return out
