"""Learned sigma (one source for every engine). Pure functions; calibrate.py runs them daily.

Sigma is the noise in a game's final margin around the expected margin. It is measured, not grid-searched on
picks, because a Brier grid search on uninformative edges just drives sigma to its upper bound
(see intelligence/validation/sigma_walk_forward.md).

Base sigma, per league:
    recency-weighted residual SD of (actual margin - line), from
      - data/history (closing line, past seasons, weight 0.5 ** seasons_ago)
      - graded Ledger games (locked Splash line, weight 1.0)
    shrunk toward the owner-approved prior (NCAAF 15.0, NFL 12.5) with PRIOR_GAMES pseudo-games,
    clipped to SIGMA_RANGE, and moved at most MAX_STEP per run (except when the current value is outside the range).

Context multipliers: games where injuries, quarterback status, weather or a big spread add uncertainty get their
own sigma. Each segment's multiplier = segment residual SD / base residual SD, shrunk toward 1.0 with
SEG_PRIOR_GAMES, clipped to SEG_RANGE, and applied only after SEG_MIN games. Below the minimum it stays 1.0.
"""
from __future__ import annotations

import csv
import glob
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
HIST = os.path.join(HERE, "data", "history")
PRIOR = {"NCAAF": 15.0, "NFL": 12.5}           # owner-approved 2026-11-02
SIGMA_RANGE = {"NCAAF": (12.0, 18.0), "NFL": (10.0, 15.0)}
PRIOR_GAMES = 100
MAX_STEP = 0.5
SEG_MIN = 30
SEG_PRIOR_GAMES = 50
SEG_RANGE = (0.85, 1.25)
SEGMENTS = ("injury_heavy", "qb_uncertain", "weather", "big_spread")
INJURY_HEAVY_PTS = 3.0     # combined injury points (both teams) at or above this
WEATHER_SEV = 0.5
BIG_SPREAD = 14.0


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def segments_for(line: float | None, detail: dict | None) -> list[str]:
    """Context segments a game falls in. detail is the Ledger Factor Detail (may be None)."""
    seg = []
    if line is not None and abs(line) > BIG_SPREAD:
        seg.append("big_spread")
    d = detail or {}
    if d:
        if (abs(_f(d.get("home_inj_pts")) or 0.0) + abs(_f(d.get("away_inj_pts")) or 0.0)) >= INJURY_HEAVY_PTS:
            seg.append("injury_heavy")
        qbf = d.get("qb_feed") or {}
        if d.get("home_qb_listed") or d.get("away_qb_listed") or any((_f(v) or 0) > 0 for v in qbf.values()):
            seg.append("qb_uncertain")
        if (_f(d.get("weather_sev")) or 0.0) >= WEATHER_SEV:
            seg.append("weather")
    return seg


def history_residuals(league: str, current_season: int) -> list[tuple[float, float, list[str]]]:
    """(residual, weight, segments) from data/history closing lines, recency-weighted."""
    out = []
    for path in glob.glob(os.path.join(HIST, f"{league.lower()}_*.csv")):
        with open(path, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                line, hs, as_ = _f(r.get("close_home_margin_line")), _f(r.get("home_score")), _f(r.get("away_score"))
                season = int(_f(r.get("season")) or current_season)
                if None in (line, hs, as_):
                    continue
                w = 0.5 ** max(current_season - season, 0)
                out.append(((hs - as_) - line, w, segments_for(line, None)))
    return out


def ledger_residuals(fs: list[dict]) -> list[tuple[float, float, list[str]]]:
    """(residual, weight 1.0, segments) from graded Ledger games: actual margin minus locked Splash line."""
    out = []
    for f in fs:
        hs, as_, line = _f(f.get("Home Score")), _f(f.get("Away Score")), _f(f.get("Vegas Implied Home Margin"))
        if None in (hs, as_, line):
            continue
        try:
            d = json.loads(f.get("Factor Detail") or "")
        except (TypeError, ValueError):
            d = None
        out.append(((hs - as_) - line, 1.0, segments_for(line, d)))
    return out


def _wsd(rows) -> tuple[float, float]:
    """Weighted residual SD (around 0: the line is the expected margin) and effective sample size."""
    sw = sum(w for _, w, _ in rows)
    if sw <= 0:
        return 0.0, 0.0
    var = sum(w * r * r for r, w, _ in rows) / sw
    n_eff = sw * sw / sum(w * w for _, w, _ in rows)
    return math.sqrt(var), n_eff


def learn(league: str, ledger_fs: list[dict], current: float | None, current_season: int,
          history: list | None = None) -> dict:
    """Returns {'sigma', 'raw', 'n_eff', 'segments': {name: {'mult', 'n', 'sd'}}, 'reason'}."""
    rows = (history if history is not None else history_residuals(league, current_season)) + ledger_residuals(ledger_fs)
    prior = PRIOR[league]
    lo, hi = SIGMA_RANGE[league]
    if not rows:
        return {"sigma": prior, "raw": None, "n_eff": 0, "segments": {}, "reason": "no data; prior"}
    raw, n_eff = _wsd(rows)
    target = (n_eff * raw + PRIOR_GAMES * prior) / (n_eff + PRIOR_GAMES)
    target = min(max(target, lo), hi)
    if current is None or not (lo <= float(current) <= hi):
        new, reason = target, f"current {current} outside {lo}-{hi}; reset to learned value"
    else:
        step = max(-MAX_STEP, min(MAX_STEP, target - float(current)))
        new, reason = float(current) + step, f"moved toward learned {target:.2f} (max step {MAX_STEP})"
    segs = {}
    for name in SEGMENTS:
        sr = [x for x in rows if name in x[2]]
        if len(sr) < SEG_MIN:
            segs[name] = {"mult": 1.0, "n": len(sr), "sd": None, "applied": False}
            continue
        sd, ne = _wsd(sr)
        m = (ne * (sd / raw) + SEG_PRIOR_GAMES * 1.0) / (ne + SEG_PRIOR_GAMES) if raw > 0 else 1.0
        segs[name] = {"mult": round(min(max(m, SEG_RANGE[0]), SEG_RANGE[1]), 3), "n": len(sr), "sd": round(sd, 2), "applied": True}
    return {"sigma": round(new, 2), "raw": round(raw, 2), "target": round(target, 2), "n_eff": round(n_eff, 1),
            "n_ledger": len(ledger_residuals(ledger_fs)), "segments": segs, "reason": reason}


def clean(league: str, value) -> float:
    """Stored sigma if it is inside the approved range, else the prior (guards stale values such as the old 20)."""
    lo, hi = SIGMA_RANGE.get(league, (10.0, 18.0))
    v = _f(value)
    return v if v is not None and lo <= v <= hi else PRIOR.get(league, 15.0)


def sigma_for(base: float, line: float | None, detail: dict | None, learned_segments: dict | None) -> tuple[float, list[str]]:
    """Game-specific sigma: base x product of applied segment multipliers. Returns (sigma, segments used)."""
    s, used = float(base), []
    for name in segments_for(line, detail):
        seg = (learned_segments or {}).get(name) or {}
        if seg.get("applied") and seg.get("mult"):
            s *= float(seg["mult"])
            used.append(f"{name} x{float(seg['mult']):.2f}")
    return s, used


# ----------------------------------------------------------------------------- shared params file
PARAMS_PATH = os.path.join(HERE, "intelligence", "learning_params.json")


def read_params(path: str | None = None) -> dict:
    try:
        with open(path or PARAMS_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def write_params(update: dict, path: str | None = None) -> None:
    """Merge one section (e.g. {'sigma': {...}}) into learning_params.json, keeping the other sections."""
    p = path or PARAMS_PATH
    cur = read_params(p)
    for k, v in update.items():
        if isinstance(v, dict) and isinstance(cur.get(k), dict):
            cur[k].update(v)
        else:
            cur[k] = v
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(cur, fh, indent=1, sort_keys=True)
