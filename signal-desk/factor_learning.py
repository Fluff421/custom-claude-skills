"""Learning for the factor model (pure functions; calibrate.py calls them).

Three questions, all answered from graded games with final scores, all gated by sample minimums:

1. Market blend k: is the FPI model adding information beyond the Splash line?
       (actual_margin - vegas) = k * (model_margin - vegas) + noise
   k near 0 means the line already contains what the model knows; k near 1 means the model is as good
   as the market. A weak prior (k ~ 0.3 +/- 0.3) is combined with the data, then clipped to [0, 1].
2. Factor scales: do the prior injury and situational points help? A joint regression of
       (actual_margin - model_margin) = s_inj * inj_pts + s_situ * situ_pts + noise
   with each scale shrunk toward 1.0 (prior sd 0.5), clipped to [0, 1.5].
3. Scorecard: base vs adjusted margin error and ATS direction on the same games.

Nothing here changes a pick. calibrate.py writes the outputs to Model Parameters only when the minimums
are met; going live (FACTOR_MODE=live) is a separate human decision.
"""
from __future__ import annotations

import json
import math

MIN_GAMES = 30          # graded games with scores (and parsed factors where needed), per league
MIN_NONZERO_INJ = 10    # games where the injury adjustment was not ~0
MIN_NONZERO_SITU = 10
K_PRIOR_MEAN, K_PRIOR_SD = 0.3, 0.3
SCALE_PRIOR_MEAN, SCALE_PRIOR_SD = 1.0, 0.5
SCALE_RANGE = (0.0, 1.5)
GO_LIVE_MIN_RMSE_GAIN = 0.25  # adjusted model must beat base by this many points of margin error


def _num(x):
    return float(x) if x is not None and x != "" else None


def game_rows(fs: list[dict]) -> list[dict]:
    """Normalise graded ledger rows that have scores, FPI, HFA and a line."""
    out = []
    for f in fs:
        hs, as_, hf, af, vg = (_num(f.get("Home Score")), _num(f.get("Away Score")), _num(f.get("Home FPI")),
                               _num(f.get("Away FPI")), _num(f.get("Vegas Implied Home Margin")))
        if None in (hs, as_, hf, af, vg):
            continue
        hfa = _num(f.get("HFA"))
        if hfa is None:
            hfa = 2.5 if f.get("League") == "NCAAF" else 2.0
        row = {"actual": hs - as_, "model": hf - af + hfa, "vegas": vg, "inj": None, "situ": None}
        try:
            d = json.loads(f.get("Factor Detail") or "")
            row["inj"] = float(d["away_inj_pts"]) - float(d["home_inj_pts"])
            la = d.get("lookahead") or {}
            if d.get("situ_parts"):  # v2+: per-factor unscaled points (look-ahead, rest, travel, revenge, weather)
                row["parts"] = {k: float(v) for k, v in d["situ_parts"].items()}
            else:
                pts = float(d.get("situ_points", 0.0))
                row["parts"] = {"lookahead": (pts if la.get("away") else 0.0) - (pts if la.get("home") else 0.0)}
            row["situ"] = sum(row["parts"].values())
            row["parsed"] = bool(d.get("inj_parsed"))
        except (ValueError, KeyError, TypeError):
            pass
        out.append(row)
    return out


def _posterior_1d(xs, ys, prior_mean, prior_sd):
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    n = len(xs)
    raw = sxy / sxx if sxx > 0 else 0.0
    res = [y - raw * x for x, y in zip(xs, ys)]
    var = max(1.0, sum(e * e for e in res) / max(1, n - 1))
    prec = sxx / var + 1.0 / prior_sd ** 2
    mean = (sxy / var + prior_mean / prior_sd ** 2) / prec
    return {"raw": raw, "raw_se": math.sqrt(var / sxx) if sxx > 0 else float("inf"), "post": mean,
            "post_sd": math.sqrt(1.0 / prec), "n": n}


def market_blend(rows: list[dict]) -> dict:
    xs = [r["model"] - r["vegas"] for r in rows]
    ys = [r["actual"] - r["vegas"] for r in rows]
    n = len(rows)
    if n < MIN_GAMES:
        return {"ok": False, "n": n, "why": f"need {MIN_GAMES} graded games with scores, have {n}"}
    p = _posterior_1d(xs, ys, K_PRIOR_MEAN, K_PRIOR_SD)
    return {"ok": True, "n": n, "k_raw": round(p["raw"], 3), "k_raw_se": round(p["raw_se"], 3),
            "k": round(min(1.0, max(0.0, p["post"])), 3), "k_post_sd": round(p["post_sd"], 3)}


FACTOR_KEYS = ("lookahead", "rest", "travel", "revenge", "weather")


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting (small systems)."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        for r in range(c + 1, n):
            f = m[r][c] / m[c][c]
            for k in range(c, n + 1):
                m[r][k] -= f * m[c][k]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (m[i][n] - sum(m[i][j] * x[j] for j in range(i + 1, n))) / m[i][i]
    return x


def _inverse_diag(a: list[list[float]]) -> list[float]:
    n = len(a)
    out = []
    for j in range(n):
        e = [1.0 if i == j else 0.0 for i in range(n)]
        out.append(_solve(a, e)[j])
    return out


def factor_scales(rows: list[dict]) -> dict:
    """Joint ridge, one scale per factor (injury plus each situational factor), each shrunk toward 1.0.
    A situational factor is only fitted when it was non-zero in at least MIN_NONZERO_SITU games; the others keep their prior."""
    use = [r for r in rows if r.get("inj") is not None and r.get("parsed")]
    n = len(use)
    if n < MIN_GAMES:
        return {"ok": False, "n": n, "why": f"need {MIN_GAMES} games with usable factor records, have {n}"}
    nz_inj = sum(1 for r in use if abs(r["inj"]) > 0.25)
    if nz_inj < MIN_NONZERO_INJ:
        return {"ok": False, "n": n, "why": f"injury adjustment non-zero in {nz_inj} games, need {MIN_NONZERO_INJ}"}
    y = [r["actual"] - r["model"] for r in use]
    names, cols, nz = ["inj"], [[r["inj"] for r in use]], {"inj": nz_inj}
    for k in FACTOR_KEYS:
        col = [(r.get("parts") or {}).get(k, 0.0) for r in use]
        cnt = sum(1 for v in col if abs(v) > 0.0)
        nz[k] = cnt
        if cnt >= MIN_NONZERO_SITU:
            names.append(k)
            cols.append(col)
    k = len(cols)
    a = [[sum(ci * cj for ci, cj in zip(cols[i], cols[j])) for j in range(k)] for i in range(k)]
    b = [sum(ci * yi for ci, yi in zip(cols[i], y)) for i in range(k)]
    sol = [b[i] / a[i][i] if a[i][i] > 0 else 0.0 for i in range(k)]
    res = [yi - sum(sol[i] * cols[i][t] for i in range(k)) for t, yi in enumerate(y)]
    var = max(1.0, sum(e * e for e in res) / max(1, n - k))
    lam = var / SCALE_PRIOR_SD ** 2
    for i in range(k):
        a[i][i] += lam
        b[i] += lam * SCALE_PRIOR_MEAN
    s = _solve(a, b)
    sd = [math.sqrt(var * v) for v in _inverse_diag(a)]
    lo, hi = SCALE_RANGE
    out = {"ok": True, "n": n, "nonzero": nz, "nonzero_inj": nz_inj, "fitted": names}
    for nm, sv, sdv in zip(names, s, sd):
        key = "inj" if nm == "inj" else nm
        out[f"scale_{key}"] = round(min(hi, max(lo, sv)), 3)
        out[f"scale_{key}_sd"] = round(sdv, 3)
    if "scale_lookahead" in out:  # legacy name used by picks.py / Model Parameters
        out["scale_situ"], out["scale_situ_sd"] = out["scale_lookahead"], out["scale_lookahead_sd"]
    return out


def scorecard(rows: list[dict]) -> dict:
    use = [r for r in rows if r.get("inj") is not None and r.get("parsed")]
    n = len(use)
    if n == 0:
        return {"n": 0}

    def rmse(pred):
        return math.sqrt(sum((r["actual"] - pred(r)) ** 2 for r in use) / n)

    def ats(pred):  # share of non-push games where the side implied by the prediction covered
        hits = tot = 0
        for r in use:
            cover = r["actual"] - r["vegas"]
            edge = pred(r) - r["vegas"]
            if cover == 0 or edge == 0:
                continue
            tot += 1
            hits += (cover > 0) == (edge > 0)
        return (hits / tot if tot else None), tot

    base = rmse(lambda r: r["model"])
    adj = rmse(lambda r: r["model"] + r["inj"] + (r["situ"] or 0.0))
    line = rmse(lambda r: r["vegas"])
    ab, nb = ats(lambda r: r["model"])
    aa, na = ats(lambda r: r["model"] + r["inj"] + (r["situ"] or 0.0))
    return {"n": n, "rmse_base": round(base, 2), "rmse_adjusted": round(adj, 2), "rmse_line": round(line, 2),
            "ats_base": None if ab is None else round(ab, 3), "ats_adjusted": None if aa is None else round(aa, 3),
            "ats_n": nb, "ready_for_review": bool(n >= MIN_GAMES and base - adj >= GO_LIVE_MIN_RMSE_GAIN)}


def summary_text(league: str, mb: dict, fs_: dict, sc: dict, now: str) -> str:
    lines = [f"{league} factor scorecard {now} (shadow; picks unchanged)"]
    lines.append("market blend: " + (f"k={mb['k']} (raw {mb['k_raw']} +/- {mb['k_raw_se']}, n={mb['n']}); 0 = line already has what the model knows"
                                      if mb.get("ok") else mb.get("why", "n/a")))
    if fs_.get("ok"):
        parts = [f"{k} {fs_['scale_' + k]} (sd {fs_['scale_' + k + '_sd']})" for k in ["inj"] + list(FACTOR_KEYS) if f"scale_{k}" in fs_]
        skipped = [k for k in FACTOR_KEYS if f"scale_{k}" not in fs_]
        lines.append("factor scales: " + ", ".join(parts) + f", n={fs_['n']}"
                     + (f"; not enough non-zero games yet: {', '.join(skipped)}" if skipped else ""))
    else:
        lines.append("factor scales: " + fs_.get("why", "n/a"))
    if sc.get("n"):
        lines.append(f"margin RMSE base {sc['rmse_base']} vs adjusted {sc['rmse_adjusted']} vs line {sc['rmse_line']} (n={sc['n']}); "
                     f"ATS base {sc['ats_base']} vs adjusted {sc['ats_adjusted']} (n={sc['ats_n']})")
    else:
        lines.append("scorecard: no graded games with factor records yet")
    return "\n".join(lines)
