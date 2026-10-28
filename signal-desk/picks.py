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

LEDGER = "tbl3tFHFhvyNMpksE"
AUTO_BOOK = "Splash Sports (auto)"
SAMPLE_MIN = int(os.environ.get("UNIT_CAP_SAMPLE_MIN", "20"))
UNIT_CAP = float(os.environ.get("UNIT_CAP", "1.0"))
PARAMS = "tblTqY4CnU08ce1s9"
DEFAULTS = {
    "sigma": {"NCAAF": 14.0, "NFL": 13.5},
    "lean": 1.0, "strong": 2.5, "max": 4.0,
    "units": {"Lean": 0.5, "Strong Play": 1.5, "Max Play": 3.0},
    "multipliers": {},
}


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
            "sigma": float(f.get("Sigma") or DEFAULTS["sigma"].get(lg, 14.0)),
            "lean": float(f.get("Threshold Lean") or DEFAULTS["lean"]),
            "strong": float(f.get("Threshold Strong") or DEFAULTS["strong"]),
            "max": float(f.get("Threshold Max") or DEFAULTS["max"]),
            "units": {"Lean": float(f.get("Units Lean") or DEFAULTS["units"]["Lean"]),
                      "Strong Play": float(f.get("Units Strong") or DEFAULTS["units"]["Strong Play"]),
                      "Max Play": float(f.get("Units Max") or DEFAULTS["units"]["Max Play"])},
            "multipliers": mult,
        }
    for lg in ("NCAAF", "NFL"):
        out.setdefault(lg, {"sigma": DEFAULTS["sigma"][lg], "lean": DEFAULTS["lean"],
                            "strong": DEFAULTS["strong"], "max": DEFAULTS["max"],
                            "units": dict(DEFAULTS["units"]), "multipliers": {}})
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
    if counts.get((league, tier), 0) < SAMPLE_MIN:
        return min(base_units, UNIT_CAP)
    return base_units


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
    recapped = []
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%MZ")
    for r in rows:
        f = r["fields"]
        if f.get("Sharp-Sheet Tier"):
            skipped["already picked"] += 1
            # re-cap pending auto picks that were sized before the cap existed
            tier0, units0 = f.get("Sharp-Sheet Tier"), f.get("Sharp-Sheet Suggested Units")
            if (f.get("Sharp-Sheet Sportsbook") == AUTO_BOOK and f.get("Grade") in (None, "Pending")
                    and f.get("Closing Spread (Home)") is None and units0 is not None):
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
        if f.get("Vegas Implied Home Margin") is None:
            skipped["no line"] += 1
            continue
        p = params[league]
        hfa = f.get("HFA")
        if hfa is None:
            hfa = 2.5 if league == "NCAAF" else 2.0
        model = float(f["Home FPI"]) - float(f["Away FPI"]) + float(hfa)
        vegas = float(f["Vegas Implied Home Margin"])
        edge = model - vegas
        ae = abs(edge)
        if ae < p["lean"]:
            skipped["below threshold"] += 1
            continue
        tier = "Max Play" if ae >= p["max"] else ("Strong Play" if ae >= p["strong"] else "Lean")
        prob = win_prob(edge, p["sigma"])
        mult = float(p["multipliers"].get(tier, 1.0))
        prob = min(0.95, max(0.50, prob * mult))
        home_pick = edge > 0
        units = capped_units(p["units"][tier], league, tier, counts)
        new = {
            "Sharp-Sheet Tier": tier,
            "Sharp-Sheet Est. Win Prob %": round(prob, 4),
            "Sharp-Sheet Suggested Units": units,
            "Recommended Side": pick_line_text(f["Home Team"] if home_pick else f["Away Team"], vegas, home_pick),
            "Sharp-Sheet Sportsbook": "Splash Sports (auto)",
            "Sharp-Sheet Data Completeness": f"Auto pick {now} | FPI+line ok | edge {edge:+.1f} | "
                                             f"injuries: NFL auto, NCAAF manual",
        }
        updates.append({"id": r["id"], "fields": new})
        report.append(f"{f.get('Game')}: {tier} {new['Recommended Side']} "
                      f"(edge {edge:+.1f}, p {prob:.1%}, {units:g}u)")

    mode = "LIVE" if live else "DRY RUN"
    if live and updates:
        es.at_patch(base, LEDGER, token, updates)
    cap_note = "; ".join(f"{lg} {t}: {n}" for (lg, t), n in sorted(counts.items())) or "none"
    lines = [f"Mode: {mode}", f"New picks: {len(report)}", f"Units re-capped: {len(recapped)}",
             f"Skipped: {skipped}",
             f"Unit cap {UNIT_CAP:g}u until {SAMPLE_MIN} graded per tier. Graded so far: {cap_note}"]
    lines += report[:60] + recapped[:60]
    print("\n".join(lines))
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("## Picks\n\n" + "\n".join(f"- {x}" for x in lines) + "\n")


if __name__ == "__main__":
    main()
