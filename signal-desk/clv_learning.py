"""Closing-line value learning (owner-approved 2026-11-02). Pure functions; calibrate.py and picks.py call them.

Two parts.

1. CLV unit gate (live). Units are earned with realized CLV, not edge size. Per league and tier, over graded
   picks that have Sharp-Sheet CLV Points:
       earned       n >= GATE_MIN and mean CLV - 1 SE > 0         -> the tier's full units
       not earning  n >= GATE_MIN and mean CLV <= 0               -> units capped at NOT_EARNING_CAP
       unproven     otherwise                                     -> the existing sample cap (UNIT_CAP, 1.0u)

2. Predicted CLV, "move before the market" (shadow). A Bayesian linear model of how far the line will move toward
   our side between pick time and close, from what we know at pick time:
       CLV ~ b_edge * |FPI edge| + b_inj * injury pts toward our side + sum_j b_j * situational pts toward our side
   Priors: b_edge from past seasons' open-to-close movement toward FPI (data/history). That prior is an upper bound,
   because ESPN's saved projection is from game day and can share late news with the line, so its prior SD equals
   its mean. Factor betas are N(0, FACTOR_PRIOR_SD). Data: graded Ledger picks with CLV and Factor Detail. A factor
   is fitted only with FACTOR_MIN_NONZERO non-zero games, and the model only with MODEL_MIN games.
   The predicted CLV gives a shadow tier. picks.py logs it to intelligence/markets/clv_shadow.csv. calibrate.py
   scores it against realized CLV, and promotion (CLV_TIER_MODE=live) needs PROMOTE_MIN forward picks with a
   positive correlation whose 90% interval excludes 0, plus owner approval.
"""
from __future__ import annotations

import csv
import glob
import json
import math
import os
from statistics import NormalDist

HERE = os.path.dirname(os.path.abspath(__file__))
HIST = os.path.join(HERE, "data", "history")
SHADOW_PATH = os.path.join(HERE, "intelligence", "markets", "clv_shadow.csv")
TIERS = ("Lean", "Strong Play", "Max Play")
GATE_MIN = 20
NOT_EARNING_CAP = 0.5
MODEL_MIN = 30
FACTOR_MIN_NONZERO = 10
FACTOR_PRIOR_SD = 0.3
FEATURES = ("edge", "inj", "lookahead", "rest", "travel", "revenge", "weather")
CLV_THRESHOLDS = {"Lean": 0.25, "Strong Play": 0.5, "Max Play": 1.0}   # predicted CLV points, priors
PROMOTE_MIN = 30
FPI_SCALE = {"NCAAF": 13.79, "NFL": 12.38}
SHADOW_COLS = ["ts", "record_id", "league", "game", "side", "edge_tier", "edge", "pred_clv", "clv_tier", "model_n"]
N = NormalDist()


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ----------------------------------------------------------------------------- 1. unit gate
def unit_gate(fs: list[dict]) -> dict:
    """{tier: {'n', 'mean', 'se', 'status'}} from graded Ledger rows of one league."""
    out = {}
    for tier in TIERS:
        v = [_f(f.get("Sharp-Sheet CLV Points")) for f in fs
             if f.get("Sharp-Sheet Tier") == tier and f.get("Grade") in ("Win", "Loss", "Push")]
        v = [x for x in v if x is not None]
        n = len(v)
        mean = sum(v) / n if n else None
        se = (math.sqrt(sum((x - mean) ** 2 for x in v) / (n - 1)) / math.sqrt(n)) if n > 1 else None
        if n >= GATE_MIN and mean is not None and se is not None and mean - se > 0:
            status = "earned"
        elif n >= GATE_MIN and mean is not None and mean <= 0:
            status = "not earning"
        else:
            status = "unproven"
        out[tier] = {"n": n, "mean": None if mean is None else round(mean, 3), "se": None if se is None else round(se, 3),
                     "status": status}
    return out


def gated_units(base_units: float, tier: str, gate: dict | None, sample_cap_units: float) -> tuple[float, str]:
    """Units after the CLV gate. sample_cap_units is what the existing sample cap would give."""
    g = (gate or {}).get(tier) or {}
    status = g.get("status", "unproven")
    if status == "earned":
        return base_units, status
    if status == "not earning":
        return min(base_units, NOT_EARNING_CAP), status
    return sample_cap_units, status


# ----------------------------------------------------------------------------- 2. predicted CLV
def side_sign(f: dict) -> int | None:
    """+1 if the Recommended Side is the home team, -1 if away, None if not a spread pick."""
    side = (f.get("Recommended Side") or "").strip()
    if "(spread)" not in side:
        return None
    team = side.rsplit(" ", 2)[0].strip()
    if team and team == (f.get("Home Team") or "").strip():
        return 1
    if team and team == (f.get("Away Team") or "").strip():
        return -1
    return None


def features(edge_home: float, detail: dict | None, sign: int) -> dict:
    """Pick-side features. edge_home is the raw FPI edge (model - line, home positive)."""
    d = detail or {}
    parts = d.get("situ_parts") or {}
    x = {"edge": sign * edge_home,
         "inj": sign * ((_f(d.get("away_inj_pts")) or 0.0) - (_f(d.get("home_inj_pts")) or 0.0))}
    for k in FEATURES[2:]:
        x[k] = sign * (_f(parts.get(k)) or 0.0)
    return x


def training_rows(fs: list[dict]) -> list[tuple[dict, float]]:
    rows = []
    for f in fs:
        clv, sign = _f(f.get("Sharp-Sheet CLV Points")), side_sign(f)
        hf, af, vg = _f(f.get("Home FPI")), _f(f.get("Away FPI")), _f(f.get("Vegas Implied Home Margin"))
        if None in (clv, sign, hf, af, vg) or f.get("Grade") not in ("Win", "Loss", "Push"):
            continue
        hfa = _f(f.get("HFA"))
        hfa = (2.5 if f.get("League") == "NCAAF" else 2.0) if hfa is None else hfa
        try:
            d = json.loads(f.get("Factor Detail") or "")
        except (TypeError, ValueError):
            d = None
        rows.append((features(hf - af + hfa - vg, d, sign), clv))
    return rows


def history_slope(league: str, seasons: tuple = (2022, 2023, 2024, 2025)) -> dict:
    """Open-to-close line movement toward FPI per point of FPI edge at the open, from data/history."""
    xs, ys = [], []
    for path in glob.glob(os.path.join(HIST, f"{league.lower()}_*.csv")):
        with open(path, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if int(_f(r.get("season")) or 0) not in seasons:
                    continue
                o, c, gp = _f(r.get("open_home_margin_line")), _f(r.get("close_home_margin_line")), _f(r.get("fpi_home_win_pct"))
                if None in (o, c, gp):
                    continue
                m = FPI_SCALE[league] * N.inv_cdf(min(max(gp / 100.0, 0.005), 0.995))
                e = m - o
                if e == 0:
                    continue
                xs.append(abs(e))
                ys.append((c - o) * (1 if e > 0 else -1))
    if len(xs) < MODEL_MIN:
        return {"slope": 0.0, "se": None, "n": len(xs)}
    sxx = sum(x * x for x in xs)
    b = sum(x * y for x, y in zip(xs, ys)) / sxx
    sd = math.sqrt(sum((y - b * x) ** 2 for x, y in zip(xs, ys)) / (len(xs) - 1))
    return {"slope": round(b, 4), "se": round(sd / math.sqrt(sxx), 4), "n": len(xs)}


def _solve(a, b):
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        if abs(m[c][c]) < 1e-12:
            continue
        for r in range(n):
            if r != c:
                k = m[r][c] / m[c][c]
                m[r] = [x - k * y for x, y in zip(m[r], m[c])]
    return [m[i][n] / m[i][i] if abs(m[i][i]) > 1e-12 else 0.0 for i in range(n)]


def fit(fs: list[dict], league: str, hist: dict | None = None) -> dict:
    """Posterior-mean coefficients. Below MODEL_MIN the model is the history prior on the edge only."""
    hist = hist if hist is not None else history_slope(league)
    prior = {k: 0.0 for k in FEATURES}
    prior_sd = {k: FACTOR_PRIOR_SD for k in FEATURES}
    prior["edge"] = hist.get("slope") or 0.0
    prior_sd["edge"] = max(abs(prior["edge"]), 0.05)
    rows = training_rows(fs)
    nonzero = {k: sum(1 for x, _ in rows if abs(x[k]) > 1e-9) for k in FEATURES}
    active = [k for k in FEATURES if k == "edge" or nonzero[k] >= FACTOR_MIN_NONZERO]
    out = {"n": len(rows), "nonzero": nonzero, "prior": prior, "history": hist, "ok": len(rows) >= MODEL_MIN}
    if not out["ok"]:
        out["coef"] = {k: (prior[k] if k == "edge" else 0.0) for k in FEATURES}
        out["noise_sd"] = None
        out["note"] = f"{len(rows)} graded picks with CLV (< {MODEL_MIN}); using the history prior on edge only"
        return out
    ys = [y for _, y in rows]
    mean_y = sum(ys) / len(ys)
    noise = max(math.sqrt(sum((y - mean_y) ** 2 for y in ys) / max(len(ys) - 1, 1)), 0.5)
    # (X'X / s^2 + P) beta = X'y / s^2 + P mu
    a = [[sum(x[i] * x[j] for x, _ in rows) / noise ** 2 + (1 / prior_sd[i] ** 2 if i == j else 0.0) for j in active] for i in active]
    b = [sum(x[i] * y for x, y in rows) / noise ** 2 + prior[i] / prior_sd[i] ** 2 for i in active]
    beta = dict(zip(active, _solve(a, b)))
    out["coef"] = {k: round(beta.get(k, 0.0), 4) for k in FEATURES}
    out["noise_sd"] = round(noise, 3)
    out["note"] = f"fitted on {len(rows)} graded picks; active features: {', '.join(active)}"
    return out


def predict(model: dict | None, edge_home: float, detail: dict | None, sign: int) -> float:
    coef = (model or {}).get("coef") or {}
    x = features(edge_home, detail, sign)
    return round(sum(coef.get(k, 0.0) * x[k] for k in FEATURES), 3)


def clv_tier(pred: float) -> str:
    for tier in ("Max Play", "Strong Play", "Lean"):
        if pred >= CLV_THRESHOLDS[tier]:
            return tier
    return "No Play"


# ----------------------------------------------------------------------------- shadow log and forward check
def append_shadow(rows: list[dict], path: str | None = None) -> int:
    """Append-only, one row per pick decision."""
    if not rows:
        return 0
    p = path or SHADOW_PATH
    new = not os.path.exists(p) or os.path.getsize(p) == 0
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=SHADOW_COLS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerows(rows)
    return len(rows)


def forward_check(graded_by_id: dict[str, float], path: str | None = None) -> dict:
    """Correlation of the first logged predicted CLV per record with its realized CLV (forward, out of sample)."""
    p = path or SHADOW_PATH
    first: dict[str, float] = {}
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["record_id"] not in first and _f(r.get("pred_clv")) is not None:
                    first[r["record_id"]] = float(r["pred_clv"])
    pairs = [(first[k], v) for k, v in graded_by_id.items() if k in first]
    n = len(pairs)
    if n < 5:
        return {"n": n, "corr": None, "lo90": None, "ready": False}
    mx, my = sum(x for x, _ in pairs) / n, sum(y for _, y in pairs) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x, _ in pairs))
    sy = math.sqrt(sum((y - my) ** 2 for _, y in pairs))
    r = sum((x - mx) * (y - my) for x, y in pairs) / (sx * sy) if sx > 0 and sy > 0 else 0.0
    r = max(min(r, 0.999), -0.999)
    z, se = math.atanh(r), 1 / math.sqrt(max(n - 3, 1))
    lo = math.tanh(z - 1.645 * se)
    return {"n": n, "corr": round(r, 3), "lo90": round(lo, 3), "ready": n >= PROMOTE_MIN and lo > 0}
