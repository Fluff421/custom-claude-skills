"""Phase 3c: automated model calibration (continuous learning).

Daily. Reads every graded pick row, computes per league:

  - Brier score and log loss vs the pick's estimated win probability
  - A calibration table (predicted vs actual win rate by probability bucket)
  - Tier hit rates (Lean / Strong Play / Max Play) with shrinkage multipliers
    (actual rate / expected rate, clamped to [0.7, 1.3]) once a tier has 20+
    graded picks - the Calibration Log's existing 20-pick rule
  - Sigma auto-tuning: grid-searches sigma over the historical edges to minimize
    Brier score (applied only with 30+ graded picks per league)

Results are upserted into the Model Parameters table, which the pick engine
(picks.py) reads - closing the learning loop. Never touches picks or results.
Dry run by default (CALIBRATE_LIVE=1 to write).
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import espn_sync as es

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

    patches, creates, report = [], [], []
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
        # sigma tuning: recompute prob from stored edge components, grid-search sigma
        edges = []
        for f in fs:
            if f.get("Grade") not in ("Win", "Loss") or None in (f.get("Home FPI"), f.get("Away FPI"),
                                                               f.get("Vegas Implied Home Margin")):
                continue
            hfa = f.get("HFA")
            if hfa is None:
                hfa = 2.5 if league == "NCAAF" else 2.0
            model = float(f["Home FPI"]) - float(f["Away FPI"]) + float(hfa)
            edges.append((abs(model - float(f["Vegas Implied Home Margin"])), 1.0 if f["Grade"] == "Win" else 0.0))
        if len(edges) >= 30:
            def brier_sigma(sig):
                return sum((0.5 * (1 + math.erf(e / (sig * math.sqrt(2)))) - y) ** 2 for e, y in edges) / len(edges)
            best = min((round(s, 1) for s in [x / 2 for x in range(16, 41)]), key=brier_sigma)
            cur = params_by_league.get(league, {}).get("fields", {}).get("Sigma")
            lines.append(f"sigma: best {best} (current {cur}) from {len(edges)} edges")
            fields["Sigma"] = best
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
    if live:
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
