#!/usr/bin/env python3
"""Per-market learning: scorecards and gated tuning for totals, moneylines, teaser legs, parlays.

Each market has its own loop. Spreads are tuned by calibrate.py / factor_learning.py (Airtable Model Parameters);
the other markets keep their settings in intelligence/market_params.json. Every change is logged in
intelligence/learning_log.csv (market, what changed, evidence, sample size).

Guards (a market's settings are NEVER rewritten on a handful of results):
  * tuning needs >= MIN_MARKET graded picks for that league and market (30)
  * a change needs a real Brier gain (>= MIN_GAIN) and moves at most MAX_STEP per run
  * values stay inside hard bounds
Usage: python market_learning.py [--live]   (dry run by default: prints what it would change)
"""
from __future__ import annotations

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import learning_events as le  # noqa: E402
import markets as mk  # noqa: E402

OUT = os.path.join(HERE, "intelligence")
PARAMS_PATH = os.path.join(OUT, "market_params.json")
SCORE_PATH = os.path.join(OUT, "markets", "scorecards.json")
MIN_MARKET, MIN_TIER = 30, 20
MIN_GAIN, MAX_STEP, BOUNDS = 0.002, 0.15, (0.3, 1.3)
TUNABLE = ("moneyline", "total", "teaser_leg")
FACTOR_WORDS = {"weather": "weather", "qb": "QB:", "injuries": "injuries", "rest": "rest", "travel": "travel", "revenge": "revenge", "look-ahead": "look-ahead"}


def _f(v):
    try:
        return None if v in ("", None) else float(v)
    except ValueError:
        return None


def outcome_rows(picks: list[dict]) -> list[dict]:
    """Flatten the pick log to graded single-leg rows plus the legs inside parlays and teasers."""
    out = []
    for r in picks:
        res = r.get("result")
        if res not in ("Win", "Loss", "Push"):
            continue
        if r["market"] in ("spread", "total", "moneyline", "teaser_leg", "parlay", "teaser"):
            out.append({"market": r["market"], "league": r["league"], "result": res, "prob": _f(r.get("prob")), "edge": _f(r.get("edge")),
                        "edge_unit": r.get("edge_unit"), "tier": r.get("tier"), "units": _f(r.get("units_won")), "stake": _f(r.get("units")),
                        "clv": _f(r.get("clv")), "factors": r.get("factors") or ""})
        if r["market"] in ("parlay",) and r.get("legs_json"):
            for l in json.loads(r["legs_json"]):
                if l.get("result") in ("Win", "Loss", "Push"):
                    out.append({"market": "parlay_leg", "league": r["league"], "result": l["result"], "prob": _f(l.get("prob")), "edge": None,
                                "edge_unit": "", "tier": "", "units": None, "stake": None, "clv": None, "factors": ""})
    return out


def brier(rows: list[dict], s: float = 1.0) -> float | None:
    pts = [(0.5 + s * (r["prob"] - 0.5), 1.0 if r["result"] == "Win" else 0.0) for r in rows if r["result"] != "Push" and r["prob"] is not None]
    return sum((p - y) ** 2 for p, y in pts) / len(pts) if pts else None


def _bins(rows: list[dict]) -> list[dict]:
    out = []
    for lo, hi in ((0, .45), (.45, .5), (.5, .55), (.55, .6), (.6, .7), (.7, 1.01)):
        b = [r for r in rows if r["result"] != "Push" and r["prob"] is not None and lo <= r["prob"] < hi]
        if b:
            out.append({"bucket": f"{lo:.0%}-{min(hi, 1):.0%}", "n": len(b), "predicted": round(sum(r["prob"] for r in b) / len(b), 3),
                        "actual": round(sum(r["result"] == "Win" for r in b) / len(b), 3)})
    return out


def scorecard(rows: list[dict]) -> dict:
    dec = [r for r in rows if r["result"] in ("Win", "Loss")]
    n = len(dec)
    wins = sum(r["result"] == "Win" for r in dec)
    units = [r["units"] for r in rows if r["units"] is not None]
    clv = [r["clv"] for r in rows if r["clv"] is not None]
    tiers = {}
    for t in ("Max Play", "Strong Play", "Lean", "No Play"):
        tr = [r for r in dec if r["tier"] == t]
        if tr:
            tiers[t] = {"n": len(tr), "win_rate": round(sum(r["result"] == "Win" for r in tr) / len(tr), 3),
                        "units": round(sum(r["units"] or 0 for r in tr), 2), "enough": len(tr) >= MIN_TIER}
    factors = {}
    for name, word in FACTOR_WORDS.items():
        with_ = [r for r in dec if word in r["factors"]]
        without = [r for r in dec if word not in r["factors"]]
        if with_:
            factors[name] = {"n_with": len(with_), "win_rate_with": round(sum(r["result"] == "Win" for r in with_) / len(with_), 3),
                             "win_rate_without": round(sum(r["result"] == "Win" for r in without) / len(without), 3) if without else None,
                             "enough": len(with_) >= MIN_MARKET}
    return {"n": n, "wins": wins, "losses": n - wins, "pushes": len(rows) - n, "win_rate": round(wins / n, 3) if n else None,
            "units": round(sum(units), 2) if units else None, "avg_clv": round(sum(clv) / len(clv), 2) if clv else None, "n_clv": len(clv),
            "brier": None if brier(dec) is None else round(brier(dec), 4), "calibration": _bins(dec), "tiers": tiers, "factors": factors}


def all_scorecards(rows: list[dict]) -> dict:
    out = {}
    for league in sorted({r["league"] for r in rows} | {"ALL"}):
        for market in mk.MARKETS + ("parlay_leg",):
            sub = [r for r in rows if r["market"] == market and (league == "ALL" or r["league"] == league)]
            if sub:
                out.setdefault(league, {})[market] = scorecard(sub)
    return out


def tune_shrink(rows: list[dict], current: float) -> tuple[float, dict]:
    """Best probability shrink toward 50% by Brier, limited to one bounded step. Returns (new value, evidence)."""
    base = brier(rows, current)
    grid = [round(x / 20, 2) for x in range(int(BOUNDS[0] * 20), int(BOUNDS[1] * 20) + 1)]
    best = min(grid, key=lambda s: brier(rows, s))
    gain = base - brier(rows, best)
    step = max(-MAX_STEP, min(MAX_STEP, best - current))
    new = round(min(BOUNDS[1], max(BOUNDS[0], current + step)), 3)
    ok = gain >= MIN_GAIN and abs(new - current) >= 0.02
    return (new if ok else current), {"best": best, "gain": round(gain, 4), "brier_now": round(base, 4), "applied": ok}


def tune(rows: list[dict], saved: dict, today: str) -> tuple[dict, list[dict], list[str]]:
    """Returns (new saved params, change events, notes)."""
    saved = json.loads(json.dumps(saved))
    events, notes = [], []
    for league in sorted({r["league"] for r in rows}):
        for market in TUNABLE:
            sub = [r for r in rows if r["league"] == league and r["market"] == market and r["result"] != "Push" and r["prob"] is not None]
            if len(sub) < MIN_MARKET:
                notes.append(f"{league} {market}: {len(sub)} graded, need {MIN_MARKET} before tuning")
                continue
            cur = float(saved.get(league, {}).get("shrink", {}).get(market, mk.SHARED["shrink"][market]))
            new, ev = tune_shrink(sub, cur)
            notes.append(f"{league} {market}: n={len(sub)}, shrink {cur} -> {new} ({'applied' if ev['applied'] else 'no meaningful gain'}; best {ev['best']}, Brier gain {ev['gain']})")
            if ev["applied"]:
                saved.setdefault(league, {}).setdefault("shrink", {})[market] = new
                events.append(le.event(league, market, "probability shrink", cur, new,
                                       f"Brier {ev['brier_now']} -> gain {ev['gain']} at shrink {ev['best']}", len(sub), "market_learning.py", today))
    return saved, events, notes


def main() -> None:
    import datetime as dt
    live = "--live" in sys.argv
    today = dt.date.today().isoformat()
    picks = mk.read_csv(os.path.join(OUT, "markets", "picks_log.csv"))
    rows = outcome_rows(picks)
    try:
        with open(PARAMS_PATH, encoding="utf-8") as fh:
            saved = json.load(fh)
    except (OSError, ValueError):
        saved = {}
    new, events, notes = tune(rows, saved, today)
    cards = all_scorecards(rows)
    print(f"Mode: {'LIVE' if live else 'DRY RUN'}; {len(rows)} graded market rows")
    for n in notes:
        print(n)
    for e in events:
        print(f"CHANGE {e['league']} {e['market']} {e['setting']}: {e['old']} -> {e['new']} (n={e['sample_size']})")
    if live:
        os.makedirs(os.path.dirname(SCORE_PATH), exist_ok=True)
        with open(SCORE_PATH, "w", encoding="utf-8") as fh:
            json.dump({"generated": today, "scorecards": cards, "notes": notes}, fh, indent=1)
        if events:
            with open(PARAMS_PATH, "w", encoding="utf-8") as fh:
                json.dump(new, fh, indent=1, sort_keys=True)
            le.append(events)


if __name__ == "__main__":
    main()
