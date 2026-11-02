"""Phase 3b: automated pick generation for the Signal Desk Ledger.

Every 3 hours (after the ESPN sync). For each upcoming Game row with complete data
(FPI + Splash line, no pick yet), computes:

    model margin = Home FPI - Away FPI + HFA
    edge          = model margin - Splash implied home margin
    est win prob  = Normal CDF(|edge| / sigma)   (sigma per league, auto-tuned)

Tier from |edge| thresholds (Lean / Strong Play / Max Play), suggested units per tier,
and the Recommended Side in the ledger's existing text format. Only writes rows with
no Sharp-Sheet Tier (manual picks are never overwritten). Parameters come from the
Model Parameters table so the calibrator can tune them. Dry run by default
(PICKS_LIVE=1 to write).

Sample-size cap: until a league/tier has SAMPLE_MIN graded picks (default 20, the
calibrator's own tier minimum), suggested units are capped at UNIT_CAP (default 1.0).
The cap also lowers Suggested Units on existing pending auto picks that have no
closing line yet; it never changes tier, side, probability or graded rows.

Re-pricing: when the Splash line or FPI changes after a pick was written, the stored side/tier
can go stale. Each run re-checks pending AUTO picks (Splash Sports (auto), Grade pending, no
closing line, game date after today in Central time) and reports any whose side or tier changed.
It updates them (or withdraws the pick if the edge fell below Lean) only when REPRICE_LIVE=1 and
PICKS_LIVE=1. The change is recorded in Sharp-Sheet Data Completeness (was ...). Manual picks,
graded rows and games dated today or earlier are never touched.
"""
from __future__ import annotations

import datetime as dt
import math
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import espn_sync as es
import factors as fx
import sigma_learning as sg
import clv_learning as cl

LEDGER = "tbl3tFHFhvyNMpksE"
AUTO_BOOK = "Splash Sports (auto)"
SAMPLE_MIN = int(os.environ.get("UNIT_CAP_SAMPLE_MIN", "20"))
UNIT_CAP = float(os.environ.get("UNIT_CAP", "1.0"))
PARAMS = "tblTqY4CnU08ce1s9"
# Injury/situational factors: "shadow" (default) records adjusted numbers but picks use the base model;
# "live" makes picks use the adjusted edge. Never set live until MODEL.md criteria are met.
FACTOR_MODE = os.environ.get("FACTOR_MODE", "shadow").strip().lower()
DEFAULTS = {
    "sigma": dict(sg.PRIOR),  # NCAAF 15.0, NFL 12.5 (owner-approved); Model Parameters Sigma overrides
    "lean": 1.0, "strong": 2.5, "max": 4.0,
    "units": {"Lean": 0.5, "Strong Play": 1.5, "Max Play": 3.0},
    "multipliers": {},
}


# Learned context multipliers for sigma (calibrate.py writes intelligence/learning_params.json)
SIGMA_SEGMENTS = {lg: v.get("segments", {}) for lg, v in (sg.read_params().get("sigma") or {}).items()}
# CLV learning (calibrate.py): unit gate per tier (live) and predicted-CLV model (shadow unless CLV_TIER_MODE=live)
CLV_PARAMS = sg.read_params().get("clv") or {}
CLV_TIER_MODE = os.environ.get("CLV_TIER_MODE", "shadow").strip().lower()
LAST_CLV: dict = {}


def load_params(token: str) -> dict[str, dict]:
    """Model Parameters rows keyed by league, with defaults for anything missing."""
    import json as _json
    url = f"https://api.airtable.com/v0/{es.AIRTABLE_BASE}/{PARAMS}"
    page = _json.loads(es.http_get(url, es.at_headers(token)))
    out = {}
    for r in page.get("records", []):
        f = r["fields"]
        lg = f.get("League", "")
        if not lg:
            continue
        mult = {}
        if f.get("Tier Multipliers"):
            try:
                mult = _json.loads(f["Tier Multipliers"])
            except ValueError:
                pass
        out[lg] = {
            "sigma": sg.clean(lg, f.get("Sigma")),
            "lean": float(f.get("Threshold Lean") or DEFAULTS["lean"]),
            "strong": float(f.get("Threshold Strong") or DEFAULTS["strong"]),
            "max": float(f.get("Threshold Max") or DEFAULTS["max"]),
            "units": {"Lean": float(f.get("Units Lean") or DEFAULTS["units"]["Lean"]),
                      "Strong Play": float(f.get("Units Strong") or DEFAULTS["units"]["Strong Play"]),
                      "Max Play": float(f.get("Units Max") or DEFAULTS["units"]["Max Play"])},
            "multipliers": mult,
            "scale_inj": float(f.get("Factor Scale Injury") or 1.0),
            "scale_situ": float(f.get("Factor Scale Situational") or 1.0),
            "scales": {k: float(f[fld]) for k, fld in (("rest", "Factor Scale Rest"), ("travel", "Factor Scale Travel"),
                                                        ("revenge", "Factor Scale Revenge"), ("weather", "Factor Scale Weather"))
                       if f.get(fld) is not None},
            "market_k": float(f["Market Blend K"]) if f.get("Market Blend K") is not None else None,
        }
    for lg in ("NCAAF", "NFL"):
        out.setdefault(lg, {"sigma": DEFAULTS["sigma"][lg], "lean": DEFAULTS["lean"],
                            "strong": DEFAULTS["strong"], "max": DEFAULTS["max"],
                            "units": dict(DEFAULTS["units"]), "multipliers": {},
                            "scale_inj": 1.0, "scale_situ": 1.0, "market_k": None})
    return out


def graded_counts(base: str, token: str) -> dict[tuple[str, str], int]:
    """Graded (Win/Loss/Push) pick counts by (league, tier) across all weeks."""
    formula = ("AND({Record Type}='Game',{Sharp-Sheet Tier},"
               "OR({Grade}='Win',{Grade}='Loss',{Grade}='Push'))")
    counts: dict[tuple[str, str], int] = {}
    offset = None
    while True:
        url = (f"https://api.airtable.com/v0/{base}/{LEDGER}?pageSize=100&filterByFormula="
               + urllib.parse.quote(formula))
        if offset:
            url += "&offset=" + urllib.parse.quote(offset, safe="")
        page = json.loads(es.http_get(url, es.at_headers(token)))
        for r in page.get("records", []):
            f = r["fields"]
            key = (f.get("League", ""), f.get("Sharp-Sheet Tier", ""))
            counts[key] = counts.get(key, 0) + 1
        offset = page.get("offset")
        if not offset:
            return counts


def capped_units(base_units: float, league: str, tier: str, counts: dict) -> float:
    """Units are earned with closing-line value: full units only when the tier's realized CLV is positive by more
    than one standard error over 20+ graded picks; 0.5u if its mean CLV is zero or negative; otherwise the 1.0u cap."""
    gate = (CLV_PARAMS.get(league) or {}).get("gate")
    units, _status = cl.gated_units(base_units, tier, gate, min(base_units, UNIT_CAP))
    return units


def win_prob(edge: float, sigma: float) -> float:
    return 0.5 * (1.0 + math.erf(abs(edge) / (sigma * math.sqrt(2.0))))


def pick_line_text(team: str, vegas_home_margin: float, home: bool) -> str:
    """Pick-side line in the ledger's 'Team -2.5 (spread)' convention."""
    if home:
        line = -vegas_home_margin  # margin +3 (home fav) -> home -3
    else:
        line = vegas_home_margin   # margin +3 -> away +3
    line = round(float(line), 1)
    sign = "-" if line < 0 or (line == 0 and vegas_home_margin > 0) else "+"
    return f"{team} {sign}{abs(line):g} (spread)"


def evaluate(f: dict, p: dict, counts: dict, now: str, line_note: str = "") -> tuple[dict | None, float, str, float, float]:
    """Price one row. Returns (fields or None if below Lean, edge, tier, prob, units)."""
    hfa = f.get("HFA")
    if hfa is None:
        hfa = 2.5 if f.get("League") == "NCAAF" else 2.0
    model = float(f["Home FPI"]) - float(f["Away FPI"]) + float(hfa)
    vegas = float(f["Vegas Implied Home Margin"])
    edge = model - vegas
    raw_edge = edge
    factor_note = ""
    x = None
    if FACTOR_MODE == "live":
        x = fx.compute(f, central_today(), now, p.get("scale_inj", 1.0), p.get("scale_situ", 1.0), p.get("scales"))
        if x is not None:
            edge = x["adj_edge"]
            if p.get("market_k") is not None:  # shrink toward the line by the learned market blend
                edge = edge * p["market_k"]
            factor_note = f" | adj (inj {x['inj_adj']:+.1f}, situ {x['situ_adj']:+.1f})"
    ae = abs(edge)
    league = f.get("League", "")
    # Every game gets a pick so the learning loop sees all of them. Below Lean it is a paper
    # tracking pick: tier "No Play", 0 units, never counted as a bet.
    tracking = ae < p["lean"]
    tier = "No Play" if tracking else ("Max Play" if ae >= p["max"] else ("Strong Play" if ae >= p["strong"] else "Lean"))
    # a quarterback listed on the injury report without a starter check (depth chart or Grok) is low-confidence
    # information either way: cap the pick at Lean until the check arrives; re-pricing then sets the full tier
    qb_unv = ((x or {}).get("detail") or {}).get("qb_unverified") or {}
    if qb_unv and tier in ("Strong Play", "Max Play"):
        factor_note += f" | QB unverified ({', '.join(f'{k} {v}' for k, v in sorted(qb_unv.items()))}): {tier} capped at Lean"
        tier = "Lean"
    sigma, seg_used = sg.sigma_for(p["sigma"], vegas, (x or {}).get("detail"), SIGMA_SEGMENTS.get(league))
    prob = win_prob(edge, sigma)
    if seg_used:
        factor_note += f" | sigma {sigma:.1f} ({', '.join(seg_used)})"
    mult = float(p["multipliers"].get(tier, 1.0))
    prob = min(0.95, max(0.50, prob * mult))
    home_pick = edge >= 0 if tracking else edge > 0
    # predicted CLV: how far the line should move toward our side before close (injuries, situations, FPI edge)
    cmodel = (CLV_PARAMS.get(league) or {}).get("model")
    pred = cl.predict(cmodel, raw_edge, (x or {}).get("detail"), 1 if home_pick else -1)
    ctier = cl.clv_tier(pred)
    if CLV_TIER_MODE == "live" and (cmodel or {}).get("ok") and ((CLV_PARAMS.get(league) or {}).get("forward") or {}).get("ready"):
        tier, tracking = ctier, ctier == "No Play"
    factor_note += f" | pCLV {pred:+.2f} (CLV tier {ctier}, {'live' if CLV_TIER_MODE == 'live' else 'shadow'})"
    LAST_CLV.clear()
    LAST_CLV.update({"league": league, "edge_tier": tier, "edge": round(edge, 2), "pred_clv": pred, "clv_tier": ctier,
                     "model_n": (cmodel or {}).get("n", 0)})
    units = 0.0 if tracking else capped_units(p["units"][tier], league, tier, counts)
    new = {
        "Sharp-Sheet Tier": tier,
        "Sharp-Sheet Est. Win Prob %": round(prob, 4),
        "Sharp-Sheet Suggested Units": units,
        "Recommended Side": pick_line_text(f["Home Team"] if home_pick else f["Away Team"], vegas, home_pick),
        "Sharp-Sheet Sportsbook": AUTO_BOOK,
        "Sharp-Sheet Data Completeness": f"{'Tracking pick (paper, 0u)' if tracking else 'Auto pick'} {now} | FPI+line ok | edge {edge:+.1f} | "
                                         f"injuries: NFL auto, NCAAF auto (secondary){factor_note}{line_note}",
    }
    return new, edge, tier, prob, units


def central_today() -> dt.date:
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("America/Chicago")).date()
    except Exception:  # noqa: BLE001
        return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=6)).date()


def main() -> None:
    token = os.environ.get("AIRTABLE_TOKEN", "").strip()
    base = os.environ.get("AIRTABLE_BASE_ID", "").strip()
    es.AIRTABLE_BASE = base
    live = os.environ.get("PICKS_LIVE", "0").strip() == "1"
    if not (token and base):
        raise SystemExit("ERROR: AIRTABLE_TOKEN and AIRTABLE_BASE_ID must be set.")

    params = load_params(token)
    counts = graded_counts(base, token)
    rows = es.at_list(base, LEDGER, token)  # Date > yesterday, Record Type Game
    updates, report, skipped = [], [], {"no line": 0, "no fpi": 0, "already picked": 0, "below threshold": 0}
    recapped, repriced, withdrawn, stale_today = [], [], [], []
    shadow_clv: list[dict] = []
    reprice_live = live and os.environ.get("REPRICE_LIVE", "0").strip() == "1"
    today = central_today()
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%MZ")
    for r in rows:
        f = r["fields"]
        if f.get("Sharp-Sheet Tier"):
            skipped["already picked"] += 1
            # re-cap pending auto picks that were sized before the cap existed
            tier0, units0 = f.get("Sharp-Sheet Tier"), f.get("Sharp-Sheet Suggested Units")
            pending_auto = (f.get("Sharp-Sheet Sportsbook") == AUTO_BOOK and f.get("Grade") in (None, "Pending")
                            and f.get("Closing Spread (Home)") is None)
            lg0 = f.get("League", "")
            if (pending_auto and lg0 in params and f.get("Date") and f.get("Home FPI") is not None
                    and f.get("Away FPI") is not None and f.get("Vegas Implied Home Margin") is not None):
                new_f, edge0, tier_n, _prob, _u = evaluate(f, params[lg0], counts, now)
                old_side = f.get("Recommended Side", "")
                changed = (new_f is None) or new_f["Recommended Side"] != old_side or tier_n != tier0
                if changed:
                    if f["Date"][:10] <= today.isoformat():
                        stale_today.append(f"{f.get('Game')}: {tier0} {old_side} vs now "
                                           f"{(new_f or {}).get('Recommended Side', 'no pick')} (game date {f['Date'][:10]}, left unchanged)")
                    elif new_f is None:
                        withdrawn.append(f"{f.get('Game')}: withdraw {tier0} {old_side} (edge now {edge0:+.1f}, below Lean)")
                        updates_r = {"Sharp-Sheet Tier": None, "Sharp-Sheet Est. Win Prob %": None,
                                     "Sharp-Sheet Suggested Units": None, "Recommended Side": None,
                                     "Sharp-Sheet Data Completeness":
                                         f"Auto pick withdrawn {now}: line/FPI moved, edge {edge0:+.1f} below Lean | "
                                         f"was {tier0} {old_side}"}
                        if reprice_live:
                            updates.append({"id": r["id"], "fields": updates_r})
                        continue
                    else:
                        repriced.append(f"{f.get('Game')}: {tier0} {old_side} -> {tier_n} {new_f['Recommended Side']} "
                                        f"(edge {edge0:+.1f})")
                        new_f["Sharp-Sheet Data Completeness"] = (f"Auto pick re-priced {now} | edge {edge0:+.1f} | "
                                                                  f"was {tier0} {old_side}")
                        if reprice_live:
                            updates.append({"id": r["id"], "fields": new_f})
                        continue
            if (pending_auto and units0 is not None):
                new_u = capped_units(float(units0), f.get("League", ""), tier0, counts)
                if new_u < float(units0):
                    updates.append({"id": r["id"], "fields": {"Sharp-Sheet Suggested Units": new_u}})
                    recapped.append(f"{f.get('Game')}: {tier0} {float(units0):g}u -> {new_u:g}u")
            continue
        if f.get("Grade") not in (None, "Pending"):
            continue
        league = f.get("League", "")
        if league not in params:
            continue
        if f.get("Home FPI") is None or f.get("Away FPI") is None:
            skipped["no fpi"] += 1
            continue
        line_note = ""
        if f.get("Vegas Implied Home Margin") is None:
            if f.get("ESPN Spread (Home)") is None:
                skipped["no line"] += 1
                continue
            # no Splash line yet: price the paper tracking pick off the ESPN consensus line, labelled as such
            f = {**f, "Vegas Implied Home Margin": -float(f["ESPN Spread (Home)"])}
            line_note = " | priced off ESPN line (no Splash line)"
        new, edge, tier, prob, units = evaluate(f, params[league], counts, now, line_note)
        if new is None:
            skipped["below threshold"] += 1
            continue
        updates.append({"id": r["id"], "fields": new})
        shadow_clv.append({**LAST_CLV, "ts": now, "record_id": r["id"], "game": f.get("Game", ""),
                           "side": new["Recommended Side"]})
        report.append(f"{f.get('Game')}: {tier} {new['Recommended Side']} "
                      f"(edge {edge:+.1f}, p {prob:.1%}, {units:g}u)")

    # Shadow factors: record adjusted numbers for every unplayed, un-closed game (never changes a pick in shadow mode)
    shadow_live = live and os.environ.get("FACTORS_SHADOW_LIVE", "0").strip() == "1"
    shadow, shadow_unparsed = {}, 0
    for r in rows:
        f = r["fields"]
        if (f.get("Grade") not in (None, "Pending") or f.get("Closing Spread (Home)") is not None
                or f.get("Home Score") is not None or f.get("League") not in params):
            continue
        p = params[f["League"]]
        x = fx.compute(f, today, now, p.get("scale_inj", 1.0), p.get("scale_situ", 1.0), p.get("scales"))
        if x is None:
            continue
        shadow_unparsed += 0 if x["detail"]["inj_parsed"] else 1
        new_s = {"Inj Adj (Home Pts)": x["inj_adj"], "Situ Adj (Home Pts)": x["situ_adj"],
                 "Adj Model Home Margin": x["adj_model"], "Adj Edge": x["adj_edge"]}
        if any(f.get(k) != v for k, v in new_s.items()) or not f.get("Factor Detail"):
            new_s["Factor Detail"] = x["detail_json"]
            shadow[r["id"]] = new_s
    if shadow_live and shadow:
        by_id = {u["id"]: u for u in updates}
        for rid, fields in shadow.items():
            if rid in by_id:
                by_id[rid]["fields"].update(fields)
            else:
                updates.append({"id": rid, "fields": fields})
    mode = "LIVE" if live else "DRY RUN"
    if live and updates:
        es.at_patch(base, LEDGER, token, updates)
    if live and shadow_clv:
        cl.append_shadow(shadow_clv)   # append-only; the picks workflow commits intelligence/markets
    cap_note = "; ".join(f"{lg} {t}: {n}" for (lg, t), n in sorted(counts.items())) or "none"
    lines = [f"Mode: {mode}", f"New picks: {len(report)}", f"Units re-capped: {len(recapped)}",
             f"Re-price ({'LIVE' if reprice_live else 'report only'}): {len(repriced)} re-priced, "
             f"{len(withdrawn)} withdrawn, {len(stale_today)} stale but dated today or earlier (not changed)",
             f"Factors ({FACTOR_MODE}; shadow writes {'LIVE' if shadow_live else 'report only'}): "
             f"{len(shadow)} rows to update, {shadow_unparsed} without a usable Injury Notes (not treated as healthy)",
             f"Skipped: {skipped}",
             f"Unit cap {UNIT_CAP:g}u until {SAMPLE_MIN} graded per tier. Graded so far: {cap_note}",
             "CLV unit gate: " + ("; ".join(f"{lg} {t}: {g['status']} (n={g['n']}, mean {g['mean']})"
                                             for lg, v in sorted(CLV_PARAMS.items()) for t, g in (v.get("gate") or {}).items())
                                   or "not learned yet (1.0u cap applies)"),
             f"CLV tier mode: {CLV_TIER_MODE}; {len(shadow_clv)} predicted-CLV rows to log"]
    lines += report[:60] + recapped[:60]
    lines += [f"RE-PRICE {x}" for x in repriced] + [f"WITHDRAW {x}" for x in withdrawn] + [f"STALE-TODAY {x}" for x in stale_today]
    print("\n".join(lines))
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("## Picks\n\n" + "\n".join(f"- {x}" for x in lines) + "\n")


if __name__ == "__main__":
    main()
