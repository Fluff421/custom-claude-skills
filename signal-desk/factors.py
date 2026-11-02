"""Injury and situational factors for the Signal Desk model (SHADOW by default).

The base model (picks.py) is FPI + HFA vs the Splash line and ignores injuries and situation. The
market prices those, FPI mostly does not, so some "edges" are only the market knowing something the
model does not. This module turns the ledger's text fields into numbers so the gap can be measured:

    adj_model_home_margin = model_home_margin + inj_adj + situ_adj
    adj_edge              = adj_model_home_margin - vegas_home_margin

Everything here is a PRIOR ASSUMPTION until calibrate.py has enough graded rows to test it (see
MODEL.md). The prior point values below are not measured; they are conservative round numbers used
only so the learning loop has something to scale. calibrate.py learns ONE scale per factor group
(injury, situational) from graded games, shrunk toward 1.0, and only above sample minimums.

Pure functions, no network, no Airtable writes. Safe to import anywhere.
"""
from __future__ import annotations

import datetime as dt
import json
import re

import situational as sit
import weather as wx

FACTOR_VERSION = 4

# --- prior point values: spread points lost when a typical STARTER at the position is out -------------
# Assumptions, not measurements. League-specific. See MODEL.md "Factors".
POS_POINTS = {
    "NFL": {"QB": 4.0, "OL": 0.8, "WR": 0.8, "TE": 0.5, "RB": 0.5, "DL": 0.8, "LB": 0.4, "DB": 0.6, "ST": 0.2},
    "NCAAF": {"QB": 3.5, "OL": 0.7, "WR": 0.6, "TE": 0.4, "RB": 0.4, "DL": 0.6, "LB": 0.3, "DB": 0.5, "ST": 0.1},
}
TEAM_CAP = {"NFL": 9.0, "NCAAF": 8.0}  # most a single team's injury list can move the margin
# Probability the player misses the game, by reported status.
STATUS_WEIGHT = {"out": 1.0, "ir": 1.0, "doubtful": 0.75, "questionable": 0.25, "dtd": 0.2, "probable": 0.05}
# Lists include backups and depth players we cannot tell apart from starters. Non-QB listings are
# discounted for that. A listed QB gets the starter value only through the starter-check feed (ESPN depth chart
# or Grok, `QB Starter Note`). Without a check for that team, only the most likely-to-miss listed QB counts, at
# backup value: injury lists name backups and long-term IR quarterbacks, and they used to stack at 4 points each.
NON_QB_STARTER_PROB = 0.6
QB_UNVERIFIED_POINTS = {"NFL": 0.5, "NCAAF": 0.5}
STALE_DAYS = 10          # aggregator-only entry older than this is mostly stale
STALE_DISCOUNT = 0.3
LOOKAHEAD_POINTS = {"NFL": 0.5, "NCAAF": 1.0}  # prior: points lost by the team flagged as looking ahead

POS_MAP = {
    "QB": "QB", "OL": "OL", "OT": "OL", "OG": "OL", "G": "OL", "T": "OL", "C": "OL", "IOL": "OL",
    "WR": "WR", "TE": "TE", "RB": "RB", "FB": "RB", "HB": "RB",
    "DL": "DL", "DE": "DL", "DT": "DL", "NT": "DL", "EDG": "DL", "EDGE": "DL",
    "LB": "LB", "OLB": "LB", "ILB": "LB", "MLB": "LB",
    "DB": "DB", "CB": "DB", "S": "DB", "FS": "DB", "SS": "DB", "NB": "DB",
    "K": "ST", "P": "ST", "LS": "ST", "PK": "ST",
}
STATUS_MAP = {
    "out": "out", "o": "out", "ir": "ir", "injured reserve": "ir", "suspension": "out", "suspended": "out",
    "doubtful": "doubtful", "d": "doubtful", "questionable": "questionable", "q": "questionable",
    "day-to-day": "dtd", "day to day": "dtd", "probable": "probable", "p": "probable",
}
_SIDES = re.compile(r"AWAY[^:|]*:(.*?)\s\|\sHOME[^:|]*:(.*)$", re.S)
_ESPN_ENTRY = re.compile(r"^(?P<name>.+?)\s\((?P<pos>[A-Za-z]{1,4})\)\s(?P<st>[A-Za-z][A-Za-z \-]*)$")
_AUTO_ENTRY = re.compile(r"^(?P<name>.+?)\s(?P<pos>[A-Z]{1,4})\s(?P<st>OUT|IR|D|Q|P)\b(?P<rest>.*)$")
_DATE_TAG = re.compile(r"\[(?:C|both[^\]]*?Covers\s\w+)?\s*([A-Z][a-z]{2})\s(\d{1,2})\]")


def _entries(chunk: str, today: dt.date) -> list[dict]:
    out = []
    for raw in chunk.split(";"):
        e = raw.strip()
        if not e or e.lower().startswith("none listed") or re.match(r"^\+\d+ more", e):
            continue
        m = _ESPN_ENTRY.match(e)
        auto = False
        if not m:
            m = _AUTO_ENTRY.match(e)
            auto = True
        if not m:
            continue
        pos = POS_MAP.get(m.group("pos").upper())
        st = STATUS_MAP.get(m.group("st").strip().lower())
        if pos is None or st is None:
            continue
        weight = STATUS_WEIGHT[st]
        stale = False
        if auto and "[C " in e and "both" not in e:  # Covers-only entry: carries its own old date
            d = re.search(r"\[C\s([A-Z][a-z]{2})\s(\d{1,2})\]", e)
            if d:
                try:
                    when = dt.datetime.strptime(f"{d.group(1)} {d.group(2)} {today.year}", "%b %d %Y").date()
                    if when > today:  # Dec entries read in January, etc.
                        when = when.replace(year=today.year - 1)
                    stale = (today - when).days > STALE_DAYS
                except ValueError:
                    pass
        out.append({"name": m.group("name").strip(), "pos": pos, "status": st, "weight": weight, "stale": stale})
    return out


def parse_injuries(note: str | None, today: dt.date) -> dict:
    """Return {'home': [...], 'away': [...], 'parsed': bool}. Blank or unparseable notes are not 'healthy'."""
    if not note:
        return {"home": [], "away": [], "parsed": False}
    m = _SIDES.search(note)
    if not m:
        return {"home": [], "away": [], "parsed": False}
    return {"away": _entries(m.group(1), today), "home": _entries(m.group(2), today), "parsed": True}


def team_points(entries: list[dict], league: str) -> tuple[float, dict]:
    """Expected spread points lost by one team, plus a small breakdown for the audit trail."""
    table = POS_POINTS.get(league, POS_POINTS["NCAAF"])
    total, detail = 0.0, {}
    for e in entries:
        if e["pos"] == "QB" and e.get("unverified"):
            pts = QB_UNVERIFIED_POINTS.get(league, 0.5) * e["weight"]
        else:
            pts = table[e["pos"]] * e["weight"] * (1.0 if e["pos"] == "QB" else NON_QB_STARTER_PROB)
        if e["stale"]:
            pts *= STALE_DISCOUNT
        total += pts
        detail[e["pos"]] = round(detail.get(e["pos"], 0.0) + pts, 2)
    cap = TEAM_CAP.get(league, 8.0)
    return min(total, cap), detail


def lookahead_side(note: str | None) -> dict:
    n = note or ""
    return {"home": "Home side may look ahead" in n, "away": "Away side may look ahead" in n}


def compute(fields: dict, today: dt.date, now_iso: str, scale_inj: float = 1.0, scale_situ: float = 1.0,
            scales: dict | None = None) -> dict | None:
    """Shadow factors for one ledger row. None if the row lacks FPI or a line.

    Sign convention matches the ledger: margins are home minus away, so a positive adjustment favors home.
    """
    try:
        model = float(fields["Home FPI"]) - float(fields["Away FPI"]) + float(
            fields.get("HFA") if fields.get("HFA") is not None else (2.5 if fields.get("League") == "NCAAF" else 2.0))
        vegas = float(fields["Vegas Implied Home Margin"])
    except (KeyError, TypeError, ValueError):
        return None
    league = fields.get("League", "NCAAF")
    inj = parse_injuries(fields.get("Injury Notes"), today)
    # Verified quarterback starter checks (Grok feed) replace whatever the injury list says about that QB
    qbf = sit.qb_fractions(fields.get("QB Starter Note"))
    for side in ("home", "away"):
        if side in qbf:
            inj[side] = [e for e in inj[side] if e["pos"] != "QB"]
            if qbf[side] > 0:
                inj[side].append({"name": "QB (starter check)", "pos": "QB", "status": "out", "weight": qbf[side], "stale": False})
        else:  # no starter check: at most one listed QB per team, valued as a backup
            qbs = [e for e in inj[side] if e["pos"] == "QB"]
            if qbs:
                keep = max(qbs, key=lambda e: e["weight"] * (STALE_DISCOUNT if e["stale"] else 1.0))
                inj[side] = [e for e in inj[side] if e["pos"] != "QB"] + [{**keep, "unverified": True}]
    inj["parsed"] = inj["parsed"] or bool(qbf)
    h_pts, h_det = team_points(inj["home"], league)
    a_pts, a_det = team_points(inj["away"], league)
    inj_adj = (a_pts - h_pts) * scale_inj  # away injuries help home, home injuries hurt home
    la = lookahead_side(fields.get("Look-Ahead Note"))
    pts = LOOKAHEAD_POINTS.get(league, 0.0)
    la_raw = (pts if la["away"] else 0.0) - (pts if la["home"] else 0.0)
    sp = sit.situational_points(fields, league)
    sev = wx.sev_from_note(fields.get("Weather Note"))
    w_raw = wx.weather_points(model, sev)
    # per-factor scales; look-ahead falls back to the legacy single situational scale
    sc = {"lookahead": scale_situ, "rest": 1.0, "travel": 1.0, "revenge": 1.0, "weather": 1.0, **(scales or {})}
    parts = {"lookahead": la_raw, "rest": sp["rest"], "travel": sp["travel"], "revenge": sp["revenge"], "weather": w_raw}
    situ_raw = sum(parts.values())
    situ_adj = sum(parts[k] * sc[k] for k in parts)
    adj_model = model + inj_adj + situ_adj
    detail = {
        "v": FACTOR_VERSION, "at": now_iso, "inj_parsed": inj["parsed"],
        "home_inj_pts": round(h_pts, 2), "away_inj_pts": round(a_pts, 2), "home_by_pos": h_det, "away_by_pos": a_det,
        "home_qb_listed": any(e["pos"] == "QB" for e in inj["home"]), "away_qb_listed": any(e["pos"] == "QB" for e in inj["away"]),
        "lookahead": la, "situ_points": pts, "situ_raw": round(situ_raw, 2), "situ_parts": {k: round(v, 2) for k, v in parts.items()}, "weather_sev": sev, "scales": sc,
        "qb_feed": qbf, "qb_unverified": {sd: next(e["name"] for e in inj[sd] if e.get("unverified"))
                                           for sd in ("home", "away") if any(e.get("unverified") for e in inj[sd])}, "weather": fields.get("Weather Note") or "", "scale_inj": scale_inj, "scale_situ": scale_situ, "model": round(model, 2), "vegas": vegas,
        "note": "prior weights, unverified; see MODEL.md Factors",
    }
    return {
        "inj_adj": round(inj_adj, 1), "situ_adj": round(situ_adj, 1),
        "adj_model": round(adj_model, 1), "adj_edge": round(adj_model - vegas, 1),
        "detail": detail, "detail_json": json.dumps(detail, separators=(",", ":")),
    }
