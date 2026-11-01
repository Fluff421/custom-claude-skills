"""NFL quarterback starter checks from ESPN (depth chart plus the NFL injury report ESPN mirrors).

Output rows use the same schema as the Grok feed's qb_starters.csv so situational.qb_note() reads both.
Classification (one label per team):
  starter_out          QB1 on the depth chart is listed Out / IR
  starter_questionable QB1 is listed Doubtful / Questionable
  starter_playing      QB1 is not on the report (a listed backup QB does not change this)
The depth chart can lag a benching, so `verified` is "auto_espn", not "verified"; Grok-verified rows win when both exist.
Pure functions; context_sync.py does the fetching.
"""
from __future__ import annotations

import re

_INJ = re.compile(r"^(?P<name>.+?)\s\((?P<pos>[A-Za-z]{1,4})\)\s(?P<st>.+)$")


def depth_qbs(depth_payload: dict) -> list[str]:
    """Quarterback names in depth order from an ESPN depthcharts payload."""
    for item in depth_payload.get("depthchart", []):
        qb = (item.get("positions") or {}).get("qb")
        if qb and qb.get("athletes"):
            return [a.get("displayName", "") for a in qb["athletes"]]
    return []


def classify(qbs: list[str], injury_items: list[str], norm) -> tuple[str, str, str]:
    """(classification, starter, evidence) for one team. injury_items look like 'Name (QB) Out'."""
    if not qbs:
        return "unknown", "", "no QB on ESPN depth chart"
    starter = qbs[0]
    listed = []
    for it in injury_items:
        m = _INJ.match(it)
        if m and m.group("pos").upper() == "QB":
            listed.append((m.group("name"), m.group("st").strip().lower()))
    for name, st in listed:
        if norm(name) == norm(starter):
            if st in ("out", "ir", "injured reserve"):
                return "starter_out", starter, f"{starter} listed {st} (ESPN injury report)"
            if st in ("doubtful", "questionable"):
                return "starter_questionable", starter, f"{starter} listed {st} (ESPN injury report)"
    if listed:
        return "starter_playing", starter, "only a backup QB is listed: " + ", ".join(f"{n} {s}" for n, s in listed)
    return "starter_playing", starter, "QB1 on ESPN depth chart not on injury report"


def team_row(team_name: str, side: str, depth_payload: dict, injury_items: list[str], norm, today: str) -> dict:
    qbs = depth_qbs(depth_payload)
    cls, starter, ev = classify(qbs, injury_items, norm)
    return {"team": team_name, "side": side, "starter": starter, "classification": cls,
            "replacement": qbs[1] if len(qbs) > 1 and cls in ("starter_out", "starter_questionable") else "",
            "evidence_text": ev, "source_date": today, "verified": "auto_espn"}
