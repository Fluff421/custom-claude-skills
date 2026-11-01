"""Change log for every automatic setting change: intelligence/learning_log.csv.

One row per change: date, league, market, setting, old, new, evidence, sample_size, source.
Nothing here decides a change; callers decide (and enforce sample minimums) and then record it here.
"""
from __future__ import annotations

import csv
import datetime as dt
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "intelligence", "learning_log.csv")
COLS = ["date", "league", "market", "setting", "old", "new", "evidence", "sample_size", "source"]
MIN_MOVE = 0.01


def moved(old, new, tol: float = MIN_MOVE) -> bool:
    try:
        return abs(float(new) - float(old)) >= tol
    except (TypeError, ValueError):
        return old != new


def event(league: str, market: str, setting: str, old, new, evidence: str, sample_size: int, source: str, date: str | None = None) -> dict:
    return {"date": date or dt.date.today().isoformat(), "league": league, "market": market, "setting": setting,
            "old": "" if old is None else old, "new": new, "evidence": evidence, "sample_size": sample_size, "source": source}


def ensure_header(path: str | None = None) -> None:
    path = path or PATH
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            csv.DictWriter(fh, fieldnames=COLS).writeheader()


def append(events: list[dict], path: str | None = None) -> int:
    if not events:
        return 0
    path = path or PATH
    new = not os.path.exists(path) or os.path.getsize(path) == 0
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerows(events)
    return len(events)


def read(path: str | None = None) -> list[dict]:
    path = path or PATH
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))
