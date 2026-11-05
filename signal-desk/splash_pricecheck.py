#!/usr/bin/env python3
"""Pick-time check: reprice every upcoming game at the NEWEST Splash line, before the owner locks a pick.

The Pick Engine prices against the ledger's early-week import (kept fixed so locked-line grading works). Splash lines
move all week, so right before a pick the owner needs the model at the number on the Splash board now. This script
reads the newest snapshot per game from intelligence/splash_lines_log.csv and reprices spreads, totals, moneylines
(at Splash's own moneyline prices) and 6-point teaser legs with the same pricer splash_compare.py uses.

Read-only. Nothing is written to Airtable and nothing is logged as a pick. Output:
  intelligence/splash_pricecheck/<UTC yyyy-mm-dd-HHMM>.md, latest.md and latest.json

Optional env SPLASH_CHECK_GAMES: comma or semicolon separated team names to limit the check (for example
"Saints, Ole Miss"). Paper picks only; verify against your Splash line before locking.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import markets as mk  # noqa: E402
import splash_compare as sc  # noqa: E402
import splash_lines as sl  # noqa: E402

DIR = os.path.join(HERE, "intelligence", "splash_pricecheck")
STALE_H = 12
TIERS = ("Lean", "Strong Play", "Max Play")


def latest_by_game(log_rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in log_rows:
        rid = r.get("record_id")
        if rid and (rid not in out or r.get("captured_at_utc", "") > out[rid].get("captured_at_utc", "")):
            out[rid] = r
    return out


def wanted(game: str, filt: list[str]) -> bool:
    if not filt:
        return True
    g = sl.norm(game)
    return any(sl.norm(x) and sl.norm(x) in g for x in filt)


def check_game(f: dict, snap: dict, pricer, params_by_league: dict | None, factor_live: bool) -> dict:
    hm, tot = sl.fnum(snap.get("home_margin")), sl.fnum(snap.get("total"))
    imp_m, imp_t = sl.fnum(f.get("Vegas Implied Home Margin")), sl.fnum(f.get("Over/Under Line"))
    league = f.get("League") or "NCAAF"
    p = mk.load_params(league, (params_by_league or {}).get(league), None)
    out = {"game": f.get("Game"), "record_id": f["_id"], "league": league, "date": (f.get("Date") or "")[:10],
           "snapshot_id": snap.get("snapshot_id"), "captured_at_central": snap.get("captured_at_central"),
           "splash_home_margin": hm, "splash_total": tot, "import_home_margin": imp_m, "import_total": imp_t}
    home, away = f.get("Home Team"), f.get("Away Team")
    if hm is not None:
        now_s = pricer(f, "spread", "home", -hm, None) or {}
        imp_s = pricer(f, "spread", "home", -imp_m, None) if imp_m is not None else {}
        side = now_s.get("side")
        team = home if side == "home" else away if side == "away" else ""
        line = (-hm if side == "home" else hm) if side else None
        out["spread"] = {"pick": f"{team} {line:+g}" if side else "", "side": side, "tier": now_s.get("tier", ""), "prob": now_s.get("prob"),
                         "edge": now_s.get("edge"), "proj": now_s.get("proj"), "import_side": (imp_s or {}).get("side", ""),
                         "import_tier": (imp_s or {}).get("tier", "")}
        if side:
            tp = sc.teaser_leg_prob(f, {"market": "spread"}, line, line + mk.TEASER_PTS, side, p, factor_live)
            out["spread"]["teaser_leg"] = {"pick": f"{team} {line + mk.TEASER_PTS:+g} (teased)", "prob": tp}
    if tot is not None:
        t = pricer(f, "total", "over", tot, None) or {}
        if t.get("side") == "under":
            t = pricer(f, "total", "under", tot, None) or t
        ti = pricer(f, "total", "over", imp_t, None) if imp_t is not None else {}
        out["total"] = {"pick": f"{str(t.get('side', '')).title()} {tot:g}" if t.get("side") else "", "side": t.get("side"), "tier": t.get("tier", ""),
                        "prob": t.get("prob"), "edge": t.get("edge"), "proj": t.get("proj"), "import_side": (ti or {}).get("side", ""),
                        "import_tier": (ti or {}).get("tier", "")}
        if t.get("side"):
            teased = tot - mk.TEASER_PTS if t["side"] == "over" else tot + mk.TEASER_PTS
            out["total"]["teaser_leg"] = {"pick": f"{t['side'].title()} {teased:g} (teased)",
                                          "prob": sc.teaser_leg_prob(f, {"market": "total"}, tot, teased, t["side"], p, factor_live)}
    aml, hml = sl.fnum(snap.get("away_ml")), sl.fnum(snap.get("home_ml"))
    if aml is not None and hml is not None:
        ph = pricer(f, "moneyline", "home", None, hml) or {}
        pa = pricer(f, "moneyline", "away", None, aml) or {}
        best = max((x for x in ((home, hml, ph), (away, aml, pa)) if x[2].get("edge") is not None), key=lambda x: x[2]["edge"], default=None)
        if best:
            out["moneyline"] = {"pick": f"{best[0]} ML {best[1]:+g}", "tier": best[2].get("tier", ""), "prob": best[2].get("prob"),
                                "edge": best[2].get("edge"), "model_ml_side": best[2].get("side", "")}
    return out


def render(results: list[dict], snap_age_h: float | None, now: str) -> str:
    from intelligence_report import md_table
    L = [f"# Pick-time check at the newest Splash lines, {now}", "",
         "The model repriced at the line on the Splash board in the newest line dump, not the early-week import. "
         "Paper picks only; nothing here was logged as a pick. Verify against your Splash line before locking.", ""]
    if snap_age_h is not None and snap_age_h > STALE_H:
        L += [f"Warning: the newest Splash snapshot is {snap_age_h:.0f} hours old. Paste a fresh File 1 dump before relying on these numbers.", ""]
    def cell(x, k):
        v = (x or {}).get(k)
        return "" if v in (None, "") else v
    def pct(v):
        return "" if v in (None, "") else f"{float(v) * 100:.1f}%"
    rows = []
    for r in results:
        for m in ("spread", "total", "moneyline"):
            x = r.get(m)
            if not x or not x.get("pick"):
                continue
            changed = ""
            if m != "moneyline" and x.get("import_tier") and (x.get("import_tier") != x.get("tier") or x.get("import_side") != x.get("side")):
                changed = f"was {x.get('import_side')} {x.get('import_tier')} at the early line"
            rows.append([r["game"], r["date"], m, x["pick"], x.get("tier", ""), pct(x.get("prob")), cell(x, "edge"), changed])
    top = [x for x in rows if x[4] in TIERS]
    L += [f"{len(top)} Lean-or-better plays at the current Splash lines ({len(results)} games checked).", ""]
    if top:
        L += [md_table(["Game", "Date", "Market", "Pick at current line", "Tier", "Win prob", "Edge", "Change vs early line"],
                       sorted(top, key=lambda x: (sl_rank(x[4]), x[1]))), ""]
    flips = [x for x in rows if x[7]]
    if flips:
        L += ["Tier or side changed since the early-week line:", "", md_table(["Game", "Date", "Market", "Pick now", "Tier now", "Win prob", "Edge", "Before"], flips), ""]
    teas = []
    for r in results:
        for m in ("spread", "total"):
            tl = (r.get(m) or {}).get("teaser_leg")
            if tl and tl.get("prob") is not None:
                teas.append([r["game"], tl["pick"], pct(tl["prob"])])
    teas.sort(key=lambda x: -float(x[2].rstrip("%") or 0))
    if teas:
        L += ["Strongest 6-point teaser legs at the current lines (two-leg teaser break-even is about 72.4% per leg at -110):", "",
              md_table(["Game", "Teased leg", "Model win prob"], teas[:10]), ""]
    L += ["All games and markets are in latest.json."]
    return "\n".join(L) + "\n"


def sl_rank(tier: str) -> int:
    return {"Max Play": 0, "Strong Play": 1, "Lean": 2}.get(tier, 3)


def main() -> None:
    import espn_sync as es
    import intelligence_report as ir
    import picks as pk
    log_rows = sl.read_csv(sl.LOG)
    if not log_rows:
        raise SystemExit("No Splash line snapshots yet. Paste a File 1 line dump first.")
    token, base = os.environ.get("AIRTABLE_TOKEN", "").strip(), os.environ.get("AIRTABLE_BASE_ID", "").strip()
    games = sl.load_games()
    by_id = {f["_id"]: f for f in games}
    params, pp, counts = {}, {}, {}
    if token and base:
        es.AIRTABLE_BASE = base
        params = {r["fields"].get("League"): r["fields"] for r in ir.fetch(base, token, ir.PARAMS, "TRUE()")}
        try:
            pp, counts = pk.load_params(token), pk.graded_counts(base, token)
        except Exception as exc:  # noqa: BLE001
            es.warn(f"pick parameters unavailable, spreads repriced with defaults: {exc}")
    factor_live = os.environ.get("FACTOR_MODE", "").lower() == "live"
    now_dt = dt.datetime.now(dt.timezone.utc)
    now = now_dt.strftime("%Y-%m-%d %H:%MZ")
    pricer = sc.make_pricer(pp, counts, now, factor_live)
    filt = [x.strip() for x in re.split(r"[,;\n]", os.environ.get("SPLASH_CHECK_GAMES", "")) if x.strip()]
    today = ir.central_today().isoformat()
    results = []
    newest = None
    for rid, snap in latest_by_game(log_rows).items():
        f = by_id.get(rid)
        if not f or f.get("Home Score") is not None or (f.get("Date") or "")[:10] < today or not wanted(f.get("Game", ""), filt):
            continue
        t = sl.parse_utc(snap.get("captured_at_utc"))
        newest = t if newest is None or (t and t > newest) else newest
        results.append(check_game(f, snap, pricer, params, factor_live))
    results.sort(key=lambda r: (r["date"], r["league"], r["game"] or ""))
    age = (now_dt - newest).total_seconds() / 3600 if newest else None
    text = render(results, age, now)
    os.makedirs(DIR, exist_ok=True)
    with open(os.path.join(DIR, now_dt.strftime("%Y-%m-%d-%H%M") + ".md"), "w", encoding="utf-8") as fh:
        fh.write(text)
    with open(os.path.join(DIR, "latest.md"), "w", encoding="utf-8") as fh:
        fh.write(text)
    with open(os.path.join(DIR, "latest.json"), "w", encoding="utf-8") as fh:
        json.dump({"generated_at": now_dt.isoformat(), "snapshot_age_hours": None if age is None else round(age, 1), "games": results}, fh, indent=1, default=str)
    print(text)


if __name__ == "__main__":
    main()
