#!/usr/bin/env python3
"""Walk-forward validation for spread sigma and k (Phase 2). Read-only: changes no parameter, writes reports only.

Inputs : data/history/{nfl,ncaaf}_{season}.csv from history_backfill.py
Outputs: intelligence/validation/sigma_walk_forward.{md,json}

Pre-registered candidates (fixed before looking at any holdout; do not add candidates after seeing results):
  C0 current live : sigma NCAAF 20 / NFL 13.5 (Airtable / default), k NCAAF 0.162 / NFL 0.3 prior
  C1 doc value    : sigma 14 / 13.5, k as C0
  C2 residual SD  : sigma = SD(actual margin - closing line) on games before the week, k as C0
  C3 refit        : sigma as C2, k refit on games before the week (OLS of margin-line on model-line, shrunk to 0)
  C4 market       : k = 0, every cover probability 0.5 (the baseline any configuration must beat)

Model margin per game = scale * inverse-normal(ESPN pre-game FPI win projection). scale was fitted on 2026 Ledger
games where both the pregame FPI margin and the projection exist (NCAAF 13.79, residual SD 0.88 pts, n=46;
NFL 12.38, n=6). Edge = model margin - closing home margin line. P(cover of model side) = Phi(k*|edge|/sigma).

Splits: selection 2022-2024, holdout 2025 (scored once for the selected candidate), forward 2026 to date.
Expanding window by week, kickoff order, never uses a game at or after the week being predicted.
"""
from __future__ import annotations

import csv
import glob
import json
import math
import os
import random
from collections import defaultdict
from statistics import NormalDist

HERE = os.path.dirname(os.path.abspath(__file__))
HIST = os.path.join(HERE, "data", "history")
OUT = os.path.join(HERE, "intelligence", "validation")
N = NormalDist()
SCALE = {"NCAAF": 13.79, "NFL": 12.38}
C0 = {"NCAAF": {"sigma": 20.0, "k": 0.162}, "NFL": {"sigma": 13.5, "k": 0.3}}
DOC_SIGMA = {"NCAAF": 14.0, "NFL": 13.5}
K_PRIOR_SD = 0.3          # prior for the C3 k refit, centred on 0
MIN_FIT = 30              # games needed before an expanding-window estimate replaces the prior
SPLITS = {"selection": (2022, 2023, 2024), "holdout": (2025,), "forward": (2026,)}
CANDIDATES = ["C0", "C1", "C2", "C3", "C4"]
BOOT = 2000
EPS = 1e-6


def load() -> dict[str, list[dict]]:
    by = defaultdict(list)
    for path in sorted(glob.glob(os.path.join(HIST, "*.csv"))):
        for r in csv.DictReader(open(path, encoding="utf-8")):
            try:
                line = float(r["close_home_margin_line"])
                gp = float(r["fpi_home_win_pct"]) / 100.0
                hs, as_ = int(float(r["home_score"])), int(float(r["away_score"]))
            except (TypeError, ValueError, KeyError):
                continue
            lg = r["league"]
            gp = min(max(gp, 0.005), 0.995)
            g = {"league": lg, "season": int(r["season"]), "season_type": int(r["season_type"]), "week": int(r["week"]),
                 "kick": r["kickoff_utc"], "margin": hs - as_, "line": line, "open": _f(r.get("open_home_margin_line")),
                 "model": SCALE[lg] * N.inv_cdf(gp), "conf": r.get("conference_game") == "1",
                 "pm": r.get("predictor_last_modified", "")}
            g["edge"] = g["model"] - g["line"]
            g["wk"] = (g["season"], g["season_type"], g["week"])
            by[lg].append(g)
    for lg in by:
        by[lg].sort(key=lambda g: (g["kick"], g["wk"]))
    return by


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def phase(g):
    if g["season_type"] == 3:
        return "post"
    return "wk1-4" if g["week"] <= 4 else "wk5-9" if g["week"] <= 9 else "wk10+"


def resid_sd(train):
    r = [g["margin"] - g["line"] for g in train]
    m = sum(r) / len(r)
    return math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1))


def refit_k(train, sigma):
    """OLS through origin of (margin - line) on edge, shrunk toward 0 with a N(0, K_PRIOR_SD^2) prior."""
    sxx = sum(g["edge"] ** 2 for g in train)
    sxy = sum(g["edge"] * (g["margin"] - g["line"]) for g in train)
    if sxx <= 0:
        return 0.0, 0.0, 0.0
    b, var = sxy / sxx, sigma ** 2 / sxx
    k = b * K_PRIOR_SD ** 2 / (K_PRIOR_SD ** 2 + var)
    return min(max(k, 0.0), 1.0), b, math.sqrt(var)


def walk(games, lg):
    """Yield (game, {cand: (prob of model side covering, sigma, k)}, outcome) week by week, prior data only."""
    weeks = sorted({g["wk"] for g in games})
    out = []
    for wk in weeks:
        train = [g for g in games if g["wk"] < wk]
        test = [g for g in games if g["wk"] == wk]
        rsd = max(resid_sd(train), 1.0) if len(train) >= MIN_FIT else DOC_SIGMA[lg]  # floor guards degenerate samples
        k3, b3, se3 = refit_k(train, rsd) if len(train) >= MIN_FIT else (C0[lg]["k"], None, None)
        params = {"C0": (C0[lg]["sigma"], C0[lg]["k"]), "C1": (DOC_SIGMA[lg], C0[lg]["k"]),
                  "C2": (rsd, C0[lg]["k"]), "C3": (rsd, k3), "C4": (rsd, 0.0)}
        for g in test:
            cover_margin = g["margin"] - g["line"]
            if cover_margin == 0 or g["edge"] == 0:
                continue  # push or no side
            y = 1 if (cover_margin > 0) == (g["edge"] > 0) else 0
            probs = {c: (N.cdf(k * abs(g["edge"]) / s), s, k) for c, (s, k) in params.items()}
            out.append((g, probs, y))
    return out


def metrics(rows, cand):
    if not rows:
        return {}
    ps = [min(max(p[cand][0], EPS), 1 - EPS) for _, p, _ in rows]
    ys = [y for _, _, y in rows]
    ll = -sum(y * math.log(p) + (1 - y) * math.log(1 - p) for p, y in zip(ps, ys)) / len(ps)
    br = sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ps)
    buckets = defaultdict(list)
    for p, y in zip(ps, ys):
        buckets[min(int(p * 20), 19) * 5].append((p, y))
    ece = sum(len(v) * abs(sum(p for p, _ in v) / len(v) - sum(y for _, y in v) / len(v)) for v in buckets.values()) / len(ps)
    rel = [{"bucket": f"{b}-{b + 5}%", "n": len(v), "pred": round(sum(p for p, _ in v) / len(v), 4),
            "hit": round(sum(y for _, y in v) / len(v), 4)} for b, v in sorted(buckets.items())]
    return {"n": len(ps), "log_loss": round(ll, 5), "brier": round(br, 5), "ece": round(ece, 4),
            "ats_hit": round(sum(ys) / len(ys), 4), "reliability": rel}


def boot_delta(rows, a, b, seed=7):
    """Block bootstrap by week of mean log-loss difference a - b. Negative favours a."""
    by = defaultdict(list)
    for g, p, y in rows:
        pa, pb = (min(max(p[c][0], EPS), 1 - EPS) for c in (a, b))
        la = -(y * math.log(pa) + (1 - y) * math.log(1 - pa))
        lb = -(y * math.log(pb) + (1 - y) * math.log(1 - pb))
        by[g["wk"]].append(la - lb)
    blocks = list(by.values())
    rng = random.Random(seed)
    point = sum(sum(x) for x in blocks) / sum(len(x) for x in blocks)
    sims = []
    for _ in range(BOOT):
        s = [blocks[rng.randrange(len(blocks))] for _ in blocks]
        sims.append(sum(sum(x) for x in s) / sum(len(x) for x in s))
    sims.sort()
    return {"delta": round(point, 5), "lo95": round(sims[int(0.025 * BOOT)], 5), "hi95": round(sims[int(0.975 * BOOT) - 1], 5)}


def open_line_clv(rows):
    """CLV of the model side if bet at the opening line: points the close moved toward that side."""
    v = []
    for g, _, _ in rows:
        if g["open"] is None:
            continue
        e_open = g["model"] - g["open"]
        if e_open == 0:
            continue
        v.append((g["line"] - g["open"]) * (1 if e_open > 0 else -1))
    return {"n": len(v), "mean_clv_pts": round(sum(v) / len(v), 3) if v else None,
            "pct_positive": round(sum(1 for x in v if x > 0) / len(v), 4) if v else None}


def outright_sigma(games):
    """Rating-free check: log loss of P(home win) = Phi(line / sigma) on all non-tie games, per fixed sigma."""
    res = {}
    for s in (11, 12, 13, 13.5, 14, 15, 16, 16.5, 17, 18, 20):
        ll, n = 0.0, 0
        for g in games:
            if g["margin"] == 0:
                continue
            p = min(max(N.cdf(g["line"] / s), EPS), 1 - EPS)
            y = 1 if g["margin"] > 0 else 0
            ll -= y * math.log(p) + (1 - y) * math.log(1 - p)
            n += 1
        res[str(s)] = round(ll / n, 5)
    return res


def stationarity(games):
    groups = defaultdict(list)
    for g in games:
        groups["phase:" + phase(g)].append(g)
        groups["conference:" + ("yes" if g["conf"] else "no")].append(g)
        a = abs(g["line"])
        groups["spread:" + ("<=7" if a <= 7 else "7-14" if a <= 14 else ">14")].append(g)
        groups["season:" + str(g["season"])].append(g)
    return {k: {"n": len(v), "resid_sd": round(resid_sd(v), 2)} for k, v in sorted(groups.items()) if len(v) >= 30}


def leakage(games, rows):
    """FPI projection should not beat the closing line on outcomes. If it does by a lot, it saw the result."""
    out = {}
    for split, seasons in SPLITS.items():
        gs = [g for g in games if g["season"] in seasons and g["margin"] != 0]
        if not gs:
            continue
        rsd = resid_sd(gs)
        def ll(fn):
            t = 0.0
            for g in gs:
                p = min(max(fn(g), EPS), 1 - EPS)
                y = 1 if g["margin"] > 0 else 0
                t -= y * math.log(p) + (1 - y) * math.log(1 - p)
            return round(t / len(gs), 5)
        sx = sum(g["edge"] ** 2 for g in gs)
        b = sum(g["edge"] * (g["margin"] - g["line"]) for g in gs) / sx
        se = rsd / math.sqrt(sx)
        late = sum(1 for g in gs if g["pm"][:10] > g["kick"][:10])
        out[split] = {"n": len(gs), "outright_ll_market": ll(lambda g: N.cdf(g["line"] / rsd)),
                      "outright_ll_fpi": ll(lambda g: N.cdf(g["model"] / rsd)),
                      "ats_beta_fpi_vs_close": round(b, 4), "ats_beta_se": round(se, 4),
                      "predictor_modified_after_kickoff_day": late}
    return out


def main():
    data = load()
    report = {"generated_from": sorted(os.path.basename(p) for p in glob.glob(os.path.join(HIST, "*.csv"))),
              "candidates": CANDIDATES, "scale": SCALE, "leagues": {}}
    for lg, games in data.items():
        rows = walk(games, lg)
        # Opening-line variant: Splash locks an early-week line, so also score covers against the open.
        og = [{**g, "line": g["open"], "edge": g["model"] - g["open"]} for g in games if g["open"] is not None]
        orows = walk(og, lg)
        R = {"games": len(games), "scored": len(rows), "splits": {}, "deltas": {}, "leakage": leakage(games, rows),
             "outright_sigma_ll": {s: outright_sigma([g for g in games if g["season"] in yrs]) for s, yrs in SPLITS.items()},
             "stationarity": stationarity(games)}
        for split, seasons in SPLITS.items():
            sr = [r for r in rows if r[0]["season"] in seasons]
            if not sr:
                continue
            R["splits"][split] = {c: metrics(sr, c) for c in CANDIDATES}
            R["splits"][split]["open_line_clv_model_side"] = open_line_clv(sr)
            R["deltas"][split] = {f"{c}_vs_C0": boot_delta(sr, c, "C0") for c in CANDIDATES if c != "C0"}
            R["deltas"][split].update({f"{c}_vs_C4": boot_delta(sr, c, "C4") for c in CANDIDATES if c != "C4"})
        R["open_line_variant"] = {}
        for split, seasons in SPLITS.items():
            sr = [r for r in orows if r[0]["season"] in seasons]
            if sr:
                R["open_line_variant"][split] = {"metrics": {c: metrics(sr, c) for c in ("C0", "C3", "C4")},
                                                 "C0_vs_C4": boot_delta(sr, "C0", "C4"), "C3_vs_C4": boot_delta(sr, "C3", "C4")}
        R["open_line_leakage"] = leakage(og, orows)
        last = rows[-1][1] if rows else {}
        R["latest_params"] = {c: {"sigma": round(v[1], 3), "k": round(v[2], 4)} for c, v in last.items()}
        sel = R["splits"].get("selection", {})
        best = min((c for c in CANDIDATES if c in sel), key=lambda c: sel[c]["log_loss"]) if sel else None
        R["selected_on_selection_set"] = best
        R["gates"] = gates(R, best)
        report["leagues"][lg] = R
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "sigma_walk_forward.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
    with open(os.path.join(OUT, "sigma_walk_forward.md"), "w", encoding="utf-8") as fh:
        fh.write(render(report))
    print(render(report))


def gates(R, best):
    g = {}
    lk = R["leakage"]
    g["1_leakage_audit"] = all(v["outright_ll_fpi"] >= v["outright_ll_market"] - 0.01 for v in lk.values())
    d = R["deltas"].get("selection", {}).get(f"{best}_vs_C0") if best and best != "C0" else None
    g["2_selection_beats_C0_ci_excludes_0"] = bool(d and d["hi95"] < 0)
    hold = R["splits"].get("holdout", {})
    g["3_holdout_no_worse_than_C0_and_beats_C4"] = bool(best and hold and hold[best]["log_loss"] <= hold["C0"]["log_loss"]
                                                       and (best == "C4" or hold[best]["log_loss"] < hold["C4"]["log_loss"]))
    g["4_forward_30_shadow_picks_nonneg_clv"] = "pending: needs predictions_log.csv by config_hash (PR #40)"
    g["5_one_sigma_source_in_picks_and_markets"] = "pending: picks.py uses Airtable Sigma, markets.py uses sigma_margin"
    g["6_owner_approval"] = "pending"
    return g


def render(rep):
    L = ["# Sigma Walk-Forward Validation", "",
         "Read-only report. No parameter was changed. Candidates were fixed before scoring (see walk_forward.py).",
         "Probability scored: P(model's spread side covers the closing line) = Phi(k x |edge| / sigma). Pushes dropped.", ""]
    for lg, R in rep["leagues"].items():
        L += [f"## {lg}", "", f"Games with line, score and FPI projection: {R['games']}. Scored (non-push, non-zero edge): {R['scored']}.", ""]
        L += ["| Split | Candidate | n | Log loss | Brier | ECE | ATS hit |", "|---|---|---|---|---|---|---|"]
        for split, S in R["splits"].items():
            for c in CANDIDATES:
                m = S[c]
                L.append(f"| {split} | {c} | {m['n']} | {m['log_loss']:.4f} | {m['brier']:.4f} | {m['ece']:.4f} | {m['ats_hit']:.3f} |")
        L += ["", "Block-bootstrap (by week) 95% interval for mean log-loss difference. Negative favours the first candidate.", "",
              "| Split | Comparison | Delta | 95% interval |", "|---|---|---|---|"]
        for split, D in R["deltas"].items():
            for k, v in D.items():
                L.append(f"| {split} | {k} | {v['delta']:+.5f} | {v['lo95']:+.5f} to {v['hi95']:+.5f} |")
        L += ["", "Model-side CLV if bet at the opening line (points the close moved toward the model side):", ""]
        for split, S in R["splits"].items():
            c = S["open_line_clv_model_side"]
            L.append(f"- {split}: n={c['n']}, mean {c['mean_clv_pts']} pts, positive {c['pct_positive']}")
        L += ["", "Leakage audit (FPI projection vs closing line on outright results; ATS beta of FPI edge on closing-line residual):", "",
              "| Split | n | Outright LL market | Outright LL FPI | ATS beta | SE | Predictor modified after kickoff day |", "|---|---|---|---|---|---|---|"]
        for split, v in R["leakage"].items():
            L.append(f"| {split} | {v['n']} | {v['outright_ll_market']:.4f} | {v['outright_ll_fpi']:.4f} | {v['ats_beta_fpi_vs_close']:+.4f} | {v['ats_beta_se']:.4f} | {v['predictor_modified_after_kickoff_day']} |")
        L += ["", "Opening-line variant (covers scored against the opening line, the closest proxy to an early Splash lock):", "",
              "| Split | n | C0 LL | C3 LL | C4 LL | C0 ATS hit | C0 vs C4 (95%) | ATS beta vs open | SE |", "|---|---|---|---|---|---|---|---|---|"]
        for split, v in R["open_line_variant"].items():
            m, d, b = v["metrics"], v["C0_vs_C4"], R["open_line_leakage"].get(split, {})
            L.append(f"| {split} | {m['C0']['n']} | {m['C0']['log_loss']:.4f} | {m['C3']['log_loss']:.4f} | {m['C4']['log_loss']:.4f} | "
                     f"{m['C0']['ats_hit']:.3f} | {d['delta']:+.5f} ({d['lo95']:+.5f} to {d['hi95']:+.5f}) | "
                     f"{b.get('ats_beta_fpi_vs_close', 0):+.4f} | {b.get('ats_beta_se', 0):.4f} |")
        L += ["", "Rating-free sigma check, P(home wins) = Phi(closing line / sigma), log loss:", ""]
        for split, d in R["outright_sigma_ll"].items():
            if d:
                b = min(d, key=d.get)
                L.append(f"- {split}: best sigma {b} (LL {d[b]:.4f}); 13.5 {d['13.5']:.4f}, 14 {d['14']:.4f}, 16.5 {d['16.5']:.4f}, 20 {d['20']:.4f}")
        L += ["", "Residual SD of (actual margin - closing line) by segment:", "", "| Segment | n | SD |", "|---|---|---|"]
        for k, v in R["stationarity"].items():
            L.append(f"| {k} | {v['n']} | {v['resid_sd']} |")
        L += ["", f"Latest walk-forward parameters: {json.dumps(R['latest_params'])}", "",
              f"Selected on selection set (lowest log loss): **{R['selected_on_selection_set']}**", "", "Promotion gates:", ""]
        for k, v in R["gates"].items():
            L.append(f"- {k}: {v}")
        L.append("")
    return "\n".join(L)


if __name__ == "__main__":
    main()
