"""Phase 3c: automated model calibration (continuous learning).

Daily. Reads every graded pick row, computes per league:

  - Brier score and log loss vs the pick's estimated win probability
  - A calibration table (predicted vs actual win rate by probability bucket)
  - Tier hit rates (Lean / Strong Play / Max Play) with shrinkage multipliers
    (actual rate / expected rate, clamped to [0.7, 1.3]) once a tier has 20+
    graded picks - the Calibration Log's existing 20-pick rule
  - Sigma: learned residual SD of (actual margin - line) from history plus graded games, shrunk to the
    approved prior (NCAAF 15, NFL 12.5), step-limited, with context multipliers (sigma_learning.py)

Results are upserted into the Model Parameters table, which the pick engine
(picks.py) reads - closing the learning loop. Never touches picks or results.
Dry run by default (CALIBRATE_LIVE=1 to write).
"""
from __future__ import annotations

import datetime as dt
import json
import learning_events as le
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import espn_sync as es
import factor_learning as fl
import sigma_learning as sg

LEDGER = "tbl3tFHFhvyNMpksE"
PARAMS = "tblTqY4CnU08ce1s9"
TIERS = ("Max Play", "Strong Play", "Lean")
BUCKETS = [(0.5, 0.55), (0.55, 0.60), (0.60, 0.65), (0.65, 0.70), (0.70, 0.80), (0.80, 1.01)]


def brier(ps, ys):
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ps)


def log_loss(ps, ys):
    eps = 0.02
    return sum(-(y * math.log(max(p, eps)) + (1 - y) * math.log(max(1 - p, eps))) for p, y in zip(ps, ys)) / len(ps)


def main() -> None:
    token = os.environ.get("AIRTABLE_TOKEN", "").strip()
    base = os.environ.get("AIRTABLE_BASE_ID", "").strip()
    es.AIRTABLE_BASE = base
    live = os.environ.get("CALIBRATE_LIVE", "0").strip() == "1"
    # new Model Parameters fields (Factor Scorecard, Market Blend K, Factor Scale Injury/Situational) must exist first
    learn_live = live and os.environ.get("FACTORS_LEARN_LIVE", "0").strip() == "1"
    if not (token and base):
        raise SystemExit("ERROR: AIRTABLE_TOKEN and AIRTABLE_BASE_ID must be set.")

    # graded pick rows across ALL weeks (no date filter)
    import urllib.parse
    out, offset = [], None
    formula = "AND({Record Type}='Game',{Sharp-Sheet Tier})"
    while True:
        url = f"https://api.airtable.com/v0/{base}/{LEDGER}?pageSize=100&filterByFormula=" + urllib.parse.quote(formula)
        if offset:
            url += "&offset=" + urllib.parse.quote(offset, safe="")
        page = json.loads(es.http_get(url, es.at_headers(token)))
        out.extend(page.get("records", []))
        offset = page.get("offset")
        if not offset:
            break
    graded = [r for r in out if r["fields"].get("Grade") in ("Win", "Loss", "Push")]

    by_league: dict[str, list[dict]] = {}
    for r in graded:
        by_league.setdefault(r["fields"].get("League", ""), []).append(r["fields"])

    # current parameters (to preserve manual values and tune sigma)
    param_rows, poffset = [], None
    while True:
        url = f"https://api.airtable.com/v0/{base}/{PARAMS}?pageSize=100"
        ppage = json.loads(es.http_get(url, es.at_headers(token)))
        param_rows.extend(ppage.get("records", []))
        if not ppage.get("offset"):
            break
    params_by_league = {r["fields"].get("League", ""): r for r in param_rows}

    patches, creates, report, events = [], [], [], []
    sigma_out: dict = {}
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    for league, fs in sorted(by_league.items()):
        if not league:
            continue
        # metrics over rows that carry an estimated win probability
        ps, ys = [], []
        for f in fs:
            if f.get("Grade") == "Push" or f.get("Sharp-Sheet Est. Win Prob %") is None:
                continue
            ps.append(float(f["Sharp-Sheet Est. Win Prob %"]))
            ys.append(1.0 if f["Grade"] == "Win" else 0.0)
        lines = [f"{league}: {len(fs)} graded picks ({len(ps)} with est. prob)"]
        fields: dict = {}
        if len(ps) >= 5:
            br, ll = brier(ps, ys), log_loss(ps, ys)
            fields["Brier Score"], fields["Log Loss"] = round(br, 4), round(ll, 4)
            table = ["bucket | n | avg pred | actual"]
            for lo, hi in BUCKETS:
                b = [(p, y) for p, y in zip(ps, ys) if lo <= p < hi]
                if b:
                    table.append(f"{lo:.0%}-{hi:.0%} | {len(b)} | {sum(p for p, _ in b)/len(b):.1%} | "
                                 f"{sum(y for _, y in b)/len(b):.1%}")
            fields["Calibration Table"] = "\n".join(table)
            lines.append(f"Brier {br:.4f}, log loss {ll:.4f}")
        # tier rates and multipliers
        mult: dict[str, float] = {}
        for tier in TIERS:
            tf = [f for f in fs if f.get("Sharp-Sheet Tier") == tier and f.get("Grade") in ("Win", "Loss")]
            if not tf:
                continue
            rate = sum(1 for f in tf if f["Grade"] == "Win") / len(tf)
            lines.append(f"{tier}: {len(tf)} picks, {rate:.1%} actual")
            if len(tf) >= 20:
                exp = [float(f["Sharp-Sheet Est. Win Prob %"]) for f in tf
                       if f.get("Sharp-Sheet Est. Win Prob %") is not None]
                if exp:
                    m = rate / (sum(exp) / len(exp))
                    mult[tier] = round(min(1.3, max(0.7, m)), 3)
                    lines.append(f"  multiplier -> {mult[tier]:.2f}")
        if mult:
            fields["Tier Multipliers"] = json.dumps(mult)
        # sigma: learned residual SD (history closing lines + graded Ledger games), shrunk to the approved prior,
        # step-limited, with context multipliers (injuries, QB, weather, big spread). See sigma_learning.py.
        cur = params_by_league.get(league, {}).get("fields", {}).get("Sigma")
        sl = sg.learn(league, fs, cur, int(now[:4]))
        lines.append(f"sigma: {cur} -> {sl['sigma']} (raw residual SD {sl['raw']}, target {sl.get('target')}, "
                     f"n_eff {sl['n_eff']}, ledger games {sl.get('n_ledger', 0)}; {sl['reason']})")
        for name, seg in sl["segments"].items():
            lines.append(f"  sigma segment {name}: x{seg['mult']} (n={seg['n']}, {'applied' if seg['applied'] else 'below ' + str(sg.SEG_MIN) + ', stays 1.0'})")
        fields["Sigma"] = sl["sigma"]
        sigma_out[league] = {**sl, "updated": now}
        # factor learning (shadow): market blend, factor scales, scorecard. Below the minimums nothing is applied.
        grows = fl.game_rows(fs)
        mb, fsd, sc = fl.market_blend(grows), fl.factor_scales(grows), fl.scorecard(grows)
        card = fl.summary_text(league, mb, fsd, sc, now[:10])
        lines.extend(card.split("\n")[1:])
        if learn_live:
            fields["Factor Scorecard"] = card
            if mb.get("ok"):
                fields["Market Blend K"] = mb["k"]
            if fsd.get("ok"):
                fields["Factor Scale Injury"] = fsd["scale_inj"]
                if "scale_situ" in fsd:
                    fields["Factor Scale Situational"] = fsd["scale_situ"]  # look-ahead scale (legacy field name)
                for k, fld in (("rest", "Factor Scale Rest"), ("travel", "Factor Scale Travel"),
                               ("revenge", "Factor Scale Revenge"), ("weather", "Factor Scale Weather")):
                    if f"scale_{k}" in fsd:
                        fields[fld] = fsd[f"scale_{k}"]
        old_f = params_by_league.get(league, {}).get("fields", {})
        why = f"{len(fs)} graded spread picks"
        for setting, key, n in (("Sigma", "Sigma", int(sl["n_eff"])), ("Market Blend K", "Market Blend K", mb.get("n", len(fs))),
                                ("Factor Scale Injury", "Factor Scale Injury", fsd.get("n", len(fs))),
                                ("Factor Scale Situational", "Factor Scale Situational", fsd.get("n", len(fs))),
                                ("Factor Scale Rest", "Factor Scale Rest", fsd.get("n", len(fs))),
                                ("Factor Scale Travel", "Factor Scale Travel", fsd.get("n", len(fs))),
                                ("Factor Scale Revenge", "Factor Scale Revenge", fsd.get("n", len(fs))),
                                ("Factor Scale Weather", "Factor Scale Weather", fsd.get("n", len(fs)))):
            if key in fields and le.moved(old_f.get(key), fields[key]):
                events.append(le.event(league, "spread", setting, old_f.get(key), fields[key],
                                      why + ("; learned residual SD, shrunk to prior, step-limited" if key == "Sigma" else "; Brier-based fit"),
                                      n, "calibrate.py", now[:10]))
        try:
            oldm = json.loads(old_f.get("Tier Multipliers") or "{}")
        except ValueError:
            oldm = {}
        for tier, val in mult.items():
            if le.moved(oldm.get(tier), val):
                events.append(le.event(league, "spread", f"Tier multiplier {tier}", oldm.get(tier), val,
                                       "actual win rate / predicted for this tier (needs 20+ picks)", sum(1 for f in fs if f.get("Sharp-Sheet Tier") == tier), "calibrate.py", now[:10]))
        fields["Graded Picks"] = len(fs)
        fields["Last Calibrated"] = now
        fields["Notes"] = "Auto-calibrated by calibrate.py"
        if league in params_by_league:
            patches.append({"id": params_by_league[league]["id"], "fields": fields})
        else:
            fields["League"] = league
            creates.append({"fields": fields})
        report.extend(lines)

    mode = "LIVE" if live else "DRY RUN"
    report.extend(f"CHANGE {e['league']} spread {e['setting']}: {e['old']} -> {e['new']} (n={e['sample_size']})" for e in events)
    if sigma_out:
        report.append("learning_params.json sigma -> " + json.dumps({k: {"sigma": v["sigma"], "segments": {n: x["mult"] for n, x in v["segments"].items()}} for k, v in sigma_out.items()}))
    if live:
        le.append(events)   # change log (repo file; the workflow commits it)
        if sigma_out:
            sg.write_params({"sigma": sigma_out})  # repo file read by picks.py and markets.py; the workflow commits it
        if patches:
            es.http_get(f"https://api.airtable.com/v0/{base}/{PARAMS}", es.at_headers(token), "PATCH",
                        {"records": patches, "typecast": True})
        if creates:
            es.http_get(f"https://api.airtable.com/v0/{base}/{PARAMS}", es.at_headers(token), "POST",
                        {"records": creates, "typecast": True})
    print("\n".join([f"Mode: {mode}", f"Param upserts: {len(patches) + len(creates)}"] + report))
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("## Calibrate\n\n" + "\n".join(f"- {x}" for x in report) + "\n")


if __name__ == "__main__":
    main()
