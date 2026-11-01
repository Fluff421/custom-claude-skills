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
            if d.get("situ_raw") is not None:  # v2: look-ahead + rest + travel + revenge, unscaled
                row["situ"] = float(d["situ_raw"])
            else:
                pts = float(d.get("situ_points", 0.0))
                row["situ"] = (pts if la.get("away") else 0.0) - (pts if la.get("home") else 0.0)
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


def factor_scales(rows: list[dict]) -> dict:
    use = [r for r in rows if r.get("inj") is not None and r.get("parsed")]
    n = len(use)
    if n < MIN_GAMES:
        return {"ok": False, "n": n, "why": f"need {MIN_GAMES} games with usable factor records, have {n}"}
    nz_inj = sum(1 for r in use if abs(r["inj"]) > 0.25)
    nz_situ = sum(1 for r in use if abs(r["situ"] or 0.0) > 0.0)
    y = [r["actual"] - r["model"] for r in use]
    x1 = [r["inj"] for r in use]
    x2 = [r["situ"] or 0.0 for r in use]
    use_situ = nz_situ >= MIN_NONZERO_SITU
    if nz_inj < MIN_NONZERO_INJ:
        return {"ok": False, "n": n, "why": f"injury adjustment non-zero in {nz_inj} games, need {MIN_NONZERO_INJ}"}
    # joint ridge toward prior mean 1.0 (2 variables, closed form); situ dropped if too few non-zero games
    cols = [x1, x2] if use_situ else [x1]
    k = len(cols)
    a = [[sum(ci * cj for ci, cj in zip(cols[i], cols[j])) for j in range(k)] for i in range(k)]
    b = [sum(ci * yi for ci, yi in zip(cols[i], y)) for i in range(k)]
    # first pass for residual variance
    sol = [b[i] / a[i][i] if a[i][i] > 0 else 0.0 for i in range(k)]
    res = [yi - sum(sol[i] * cols[i][t] for i in range(k)) for t, yi in enumerate(y)]
    var = max(1.0, sum(e * e for e in res) / max(1, n - k))
    lam = var / SCALE_PRIOR_SD ** 2
    for i in range(k):
        a[i][i] += lam
        b[i] += lam * SCALE_PRIOR_MEAN
    if k == 1:
        s = [b[0] / a[0][0]]
        sd = [math.sqrt(var / a[0][0])]
    else:
        det = a[0][0] * a[1][1] - a[0][1] * a[1][0]
        s = [(b[0] * a[1][1] - a[0][1] * b[1]) / det, (a[0][0] * b[1] - a[1][0] * b[0]) / det]
        sd = [math.sqrt(var * a[1][1] / det), math.sqrt(var * a[0][0] / det)]
    lo, hi = SCALE_RANGE
    out = {"ok": True, "n": n, "nonzero_inj": nz_inj, "nonzero_situ": nz_situ,
           "scale_inj": round(min(hi, max(lo, s[0])), 3), "scale_inj_sd": round(sd[0], 3)}
    if use_situ:
        out.update(scale_situ=round(min(hi, max(lo, s[1])), 3), scale_situ_sd=round(sd[1], 3))
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
    lines.append("factor scales: " + (f"injury {fs_['scale_inj']} (sd {fs_['scale_inj_sd']})"
                                      + (f", situational {fs_['scale_situ']} (sd {fs_['scale_situ_sd']})" if "scale_situ" in fs_ else ", situational not enough data")
                                      + f", n={fs_['n']}" if fs_.get("ok") else fs_.get("why", "n/a")))
    if sc.get("n"):
        lines.append(f"margin RMSE base {sc['rmse_base']} vs adjusted {sc['rmse_adjusted']} vs line {sc['rmse_line']} (n={sc['n']}); "
                     f"ATS base {sc['ats_base']} vs adjusted {sc['ats_adjusted']} (n={sc['ats_n']})")
    else:
        lines.append("scorecard: no graded games with factor records yet")
    return "\n".join(lines)
