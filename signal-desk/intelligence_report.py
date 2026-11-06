#!/usr/bin/env python3
"""Daily intelligence report for the Signal Desk betting intelligence system.

Read-only against Airtable. Writes, into the repo:
  intelligence/latest.md                 human-readable daily report
  intelligence/data/YYYY-MM-DD.json      every data point behind the report
  intelligence/learning_state.csv        one row per league per day: what the spread learner currently believes (trend over time)
  intelligence/learning_log.csv          change log: every automatic change (market, setting, old, new, evidence, sample size)
It never writes Airtable, picks, or Splash fields. All picks are paper picks.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import math
import os
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import close_grade as cg  # noqa: E402
import espn_sync as es  # noqa: E402
import factor_learning as fl  # noqa: E402

LEDGER, PARAMS = "tbl3tFHFhvyNMpksE", "tblTqY4CnU08ce1s9"
OUT = os.path.join(HERE, "intelligence")
TIER_RANK = {"Max Play": 0, "Strong Play": 1, "Lean": 2, "No Play": 3}
RECENT_DAYS = 7
SAMPLE_TIER, SAMPLE_LEAGUE = 20, 30


def fetch(base: str, token: str, table: str, formula: str) -> list[dict]:
    out, offset = [], None
    while True:
        url = f"https://api.airtable.com/v0/{base}/{table}?pageSize=100&filterByFormula=" + urllib.parse.quote(formula)
        if offset:
            url += "&offset=" + urllib.parse.quote(offset, safe="")
        page = json.loads(es.http_get(url, es.at_headers(token)))
        out.extend(page.get("records", []))
        offset = page.get("offset")
        if not offset:
            return out


def central_today() -> dt.date:
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("America/Chicago")).date()
    except Exception:  # noqa: BLE001
        return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=6)).date()


def model_margin(f: dict) -> float | None:
    try:
        hfa = f.get("HFA")
        if hfa is None:
            hfa = 2.5 if f.get("League") == "NCAAF" else 2.0
        return float(f["Home FPI"]) - float(f["Away FPI"]) + float(hfa)
    except (KeyError, TypeError, ValueError):
        return None


def detail(f: dict) -> dict:
    try:
        return json.loads(f.get("Factor Detail") or "")
    except ValueError:
        return {}


def drivers_upcoming(f: dict) -> list[str]:
    """Plain-language reasons behind an upcoming pick, from the stored factor record."""
    d, out = detail(f), []
    m, v = model_margin(f), f.get("Vegas Implied Home Margin")
    if m is not None and v is not None:
        out.append(f"model margin {m:+.1f} vs line {float(v):+.1f} (base edge {m - float(v):+.1f})")
    if d.get("home_inj_pts") or d.get("away_inj_pts"):
        out.append(f"injuries: home loses {d.get('home_inj_pts', 0)} pts, away loses {d.get('away_inj_pts', 0)} pts")
    for k, label in (("rest", "rest"), ("travel", "travel"), ("revenge", "revenge"), ("lookahead", "look-ahead"), ("weather", "weather")):
        val = (d.get("situ_parts") or {}).get(k)
        if val:
            out.append(f"{label} {val:+.1f} pts to home")
    if any(w in (f.get("QB Starter Note") or "") for w in ("OUT", "QUESTIONABLE")):
        out.append("QB: " + f["QB Starter Note"])
    if f.get("Weather Note"):
        out.append("weather: " + f["Weather Note"])
    return out


def explain_result(f: dict) -> dict:
    """What the prediction data said versus what happened, and which factors moved the right way."""
    actual = f.get("Actual Home Margin")
    m = model_margin(f)
    out = {"game": f.get("Game"), "date": (f.get("Date") or "")[:10], "league": f.get("League"), "tier": f.get("Sharp-Sheet Tier"),
           "pick": f.get("Recommended Side"), "grade": f.get("Grade"), "units": f.get("Sharp-Sheet Suggested Units"),
           "prob": f.get("Sharp-Sheet Est. Win Prob %"), "clv": f.get("Sharp-Sheet CLV Points"), "actual_home_margin": actual,
           "model_margin": None if m is None else round(m, 1), "line_margin": f.get("Vegas Implied Home Margin"),
           "closing_spread_home": f.get("Closing Spread (Home)"), "notes": []}
    if actual is None or m is None:
        out["notes"].append("no final margin or no model inputs")
        return out
    actual = float(actual)
    out["model_error"] = round(actual - m, 1)
    v = f.get("Vegas Implied Home Margin")
    if v is not None:
        out["line_error"] = round(actual - float(v), 1)
        better = "the model" if abs(actual - m) < abs(actual - float(v)) else "the line"
        out["closer"] = better
        out["notes"].append(f"final home margin {actual:+g}: model missed by {abs(actual - m):.1f}, line missed by {abs(actual - float(v)):.1f} ({better} was closer)")
    d = detail(f)
    if d.get("situ_parts") or d.get("home_inj_pts") is not None:
        inj = float(d.get("away_inj_pts", 0)) - float(d.get("home_inj_pts", 0))
        parts = {"injuries": inj, **{k: float(x) for k, x in (d.get("situ_parts") or {}).items()}}
        surprise = actual - m
        helped, hurt = [], []
        for k, val in parts.items():
            if abs(val) < 0.05:
                continue
            (helped if val * surprise > 0 else hurt).append(f"{k} {val:+.1f}")
        adj = m + sum(parts.values())
        out["adjusted_margin"] = round(adj, 1)
        out["factors_helped"], out["factors_hurt"] = helped, hurt
        out["notes"].append(f"adjusted margin {adj:+.1f} ({'closer' if abs(actual - adj) < abs(surprise) else 'farther'} than base model)")
        if helped:
            out["notes"].append("factors that pointed the right way: " + ", ".join(helped))
        if hurt:
            out["notes"].append("factors that pointed the wrong way: " + ", ".join(hurt))
    else:
        out["notes"].append("no factor record (game predates shadow factors)")
    pk = cg.parse_pick(f.get("Recommended Side") or "")
    if pk and pk[0] == "spread":
        ish = cg.side_is_home(pk[1], f.get("Home Team", ""), f.get("Away Team", ""))
        if ish is not None:
            cover = (actual + pk[2]) if ish else (-actual + pk[2])
            out["cover_margin"] = round(cover, 1)
            out["notes"].append(f"pick covered by {cover:+.1f} points")
    return out


def brier(rows: list[dict]) -> float | None:
    pts = [(float(f["Sharp-Sheet Est. Win Prob %"]), 1.0 if f["Grade"] == "Win" else 0.0) for f in rows
           if f.get("Grade") in ("Win", "Loss") and f.get("Sharp-Sheet Est. Win Prob %") is not None]
    return round(sum((p - y) ** 2 for p, y in pts) / len(pts), 4) if pts else None


def tier_table(graded: list[dict]) -> list[dict]:
    out = []
    for lg in ("NCAAF", "NFL", "ALL"):
        for tier in ("Max Play", "Strong Play", "Lean", "No Play"):
            rs = [f for f in graded if (lg == "ALL" or f.get("League") == lg) and f.get("Sharp-Sheet Tier") == tier]
            w = sum(1 for f in rs if f["Grade"] == "Win")
            l_ = sum(1 for f in rs if f["Grade"] == "Loss")
            clv = [float(f["Sharp-Sheet CLV Points"]) for f in rs if f.get("Sharp-Sheet CLV Points") is not None]
            if rs:
                out.append({"league": lg, "tier": tier, "wins": w, "losses": l_, "pushes": len(rs) - w - l_,
                            "hit": round(w / (w + l_), 3) if w + l_ else None, "brier": brier(rs),
                            "avg_clv": round(sum(clv) / len(clv), 2) if clv else None, "n": len(rs)})
    return out


def edge_buckets(graded: list[dict]) -> list[dict]:
    out = []
    for lo, hi in ((0, 1), (1, 2.5), (2.5, 4), (4, 6), (6, 99)):
        rs = []
        for f in graded:
            m, v = model_margin(f), f.get("Vegas Implied Home Margin")
            if m is not None and v is not None and lo <= abs(m - float(v)) < hi and f.get("Grade") in ("Win", "Loss"):
                rs.append(f)
        w = sum(1 for f in rs if f["Grade"] == "Win")
        if rs:
            out.append({"edge": f"{lo}-{hi if hi < 99 else '+'}", "wins": w, "losses": len(rs) - w, "hit": round(w / len(rs), 3)})
    return out


def learning_state(params: list[dict], graded: list[dict]) -> list[dict]:
    rows = []
    for p in params:
        f = p["fields"]
        lg = f.get("League")
        if not lg:
            continue
        g = [x for x in graded if x.get("League") == lg]
        with_factors = sum(1 for x in g if detail(x).get("situ_parts") is not None or detail(x).get("home_inj_pts") is not None)
        rows.append({"league": lg, "sigma": f.get("Sigma"), "lean": f.get("Threshold Lean"), "strong": f.get("Threshold Strong"),
                     "max": f.get("Threshold Max"), "tier_multipliers": f.get("Tier Multipliers"), "market_k": f.get("Market Blend K"),
                     "scale_injury": f.get("Factor Scale Injury"), "scale_lookahead": f.get("Factor Scale Situational"),
                     "scale_rest": f.get("Factor Scale Rest"), "scale_travel": f.get("Factor Scale Travel"),
                     "scale_revenge": f.get("Factor Scale Revenge"), "scale_weather": f.get("Factor Scale Weather"),
                     "graded": len(g), "graded_with_factor_record": with_factors, "brier": brier(g),
                     "last_calibrated": f.get("Last Calibrated"), "scorecard": f.get("Factor Scorecard")})
    return rows


def automatic_changes(state: list[dict], graded: list[dict]) -> list[dict]:
    """What the learner will change by itself, with current progress toward each gate."""
    items = []
    for s in state:
        lg = s["league"]
        g = [x for x in graded if x.get("League") == lg]
        by_tier = {t: sum(1 for x in g if x.get("Sharp-Sheet Tier") == t and x["Grade"] in ("Win", "Loss")) for t in ("Lean", "Strong Play", "Max Play")}
        items += [
            {"league": lg, "setting": "Sigma (win-probability spread)", "now": s["sigma"], "gate": f">= {SAMPLE_LEAGUE} graded", "progress": f"{len(g)}/{SAMPLE_LEAGUE}",
             "rule": "daily grid search; picks the sigma with the best Brier score"},
            {"league": lg, "setting": "Tier win-probability multipliers", "now": s["tier_multipliers"] or "none", "gate": f">= {SAMPLE_TIER} graded per tier",
             "progress": ", ".join(f"{t} {n}/{SAMPLE_TIER}" for t, n in by_tier.items()), "rule": "actual hit rate divided by predicted, clipped 0.7 to 1.3"},
            {"league": lg, "setting": "Unit cap (1.0u) on Strong/Max", "now": "capped", "gate": f">= {SAMPLE_TIER} graded per tier", "progress": ", ".join(f"{t} {n}/{SAMPLE_TIER}" for t, n in by_tier.items()),
             "rule": "stays capped; Strong and Max remain paper picks regardless"},
            {"league": lg, "setting": "Market blend k (does the model add to the line)", "now": s["market_k"], "gate": f">= {SAMPLE_LEAGUE} graded with scores",
             "progress": f"{len(g)}/{SAMPLE_LEAGUE}", "rule": "regression of result-minus-line on model-minus-line, shrunk to a 0.3 prior"},
            {"league": lg, "setting": "Factor scales (injury, look-ahead, rest, travel, revenge, weather)",
             "now": {k: s[k] for k in ("scale_injury", "scale_lookahead", "scale_rest", "scale_travel", "scale_revenge", "scale_weather")},
             "gate": f">= {SAMPLE_LEAGUE} graded with a factor record; each factor needs 10 non-zero games", "progress": f"{s['graded_with_factor_record']}/{SAMPLE_LEAGUE}",
             "rule": "joint ridge regression toward 1.0; 0 switches the factor off"},
        ]
    return items


def data_gaps(upcoming: list[dict]) -> list[str]:
    gaps = []
    n = len(upcoming)
    if not n:
        return ["no upcoming games in the ledger"]
    no_splash = [f.get("Game") for f in upcoming if f.get("Vegas Implied Home Margin") is None]
    if no_splash:
        gaps.append(f"{len(no_splash)} of {n} upcoming games have no Splash line (tracking picks use the ESPN line): " + "; ".join(no_splash[:8]))
    no_inj = [f.get("Game") for f in upcoming if not f.get("Injury Notes")]
    if no_inj:
        gaps.append(f"{len(no_inj)} upcoming games have no injury notes")
    no_wx = [f.get("Game") for f in upcoming if not f.get("Weather Note") and not (f.get("Date") or "")[:10] > str(central_today() + dt.timedelta(days=6))]
    if no_wx:
        gaps.append(f"{len(no_wx)} games inside the forecast window have no weather note")
    ncaaf_qb = sum(1 for f in upcoming if f.get("League") == "NCAAF" and f.get("QB Starter Note"))
    ncaaf_n = sum(1 for f in upcoming if f.get("League") == "NCAAF")
    if ncaaf_n:
        gaps.append(f"NCAAF quarterback checks cover {ncaaf_qb} of {ncaaf_n} games (comes from the Grok feed only)")
    return gaps


def md_table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join("" if c is None else str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def user_vs_model(graded_by_gid: dict) -> list[dict]:
    """Owner's Splash picks, graded against the LOCKED line, with the model repriced at that line (see splash_compare.py)."""
    path = os.path.join(OUT, "splash_picks_log.csv")
    if not os.path.exists(path):
        return []
    import splash_compare as sc
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return sc.grade_log(rows, graded_by_gid)


def _model_result(r: dict, game: dict | None) -> str:
    """What the model's own side at the locked line would have done (same market, same line)."""
    side = r.get("model_side_lock")
    if not side or not game or game.get("Home Score") is None or r.get("market") in ("teaser_leg", "other"):
        return "pending"
    import markets as mk
    try:
        line = float(r["locked_line"])
    except (TypeError, ValueError):
        return "pending"
    if r["market"] == "total":
        return mk.grade_leg("total", side, line, game["Home Score"], game["Away Score"])
    if r["market"] == "moneyline":
        return mk.grade_leg("moneyline", side, 0, game["Home Score"], game["Away Score"])
    mline = line if side == r.get("side") else -line
    return mk.grade_leg("spread", side, mline, game["Home Score"], game["Away Score"])


def by_market_summary(splash: list[dict], games_by_id: dict) -> list[dict]:
    """Owner vs model by market, graded at locked lines (legs of tickets counted under their own market)."""
    out = {}
    for r in splash:
        if r["leg_result"] not in ("Win", "Loss", "Push"):
            continue
        m = out.setdefault(r["market"], {"market": r["market"], "n": 0, "you_w": 0, "you_l": 0, "model_w": 0, "model_l": 0, "against": 0})
        m["n"] += 1
        m["you_w"] += r["leg_result"] == "Win"
        m["you_l"] += r["leg_result"] == "Loss"
        mr = _model_result(r, games_by_id.get(r.get("record_id")))
        m["model_w"] += mr == "Win"
        m["model_l"] += mr == "Loss"
        m["against"] += r.get("matched") == "no"
    return list(out.values())


def timing_table(splash: list[dict]) -> list[dict]:
    """Does locking earlier or later in the week help? Buckets by days from lock to kickoff."""
    out = []
    for name, lo, hi in (("5+ days before", 5, 99), ("3-4 days before", 3, 4), ("0-2 days before", 0, 2)):
        sub = []
        for r in splash:
            try:
                d = int(r.get("lead_days"))
            except (TypeError, ValueError):
                continue
            if lo <= d <= hi and r.get("movement_for_you") not in ("", None):
                sub.append(r)
        dec = [r for r in sub if r["leg_result"] in ("Win", "Loss")]
        mv = [float(r["movement_for_you"]) for r in sub]
        out.append({"bucket": name, "n": len(sub), "avg_move_for_you": round(sum(mv) / len(mv), 2) if mv else None,
                    "graded": len(dec), "win_rate": round(sum(r["leg_result"] == "Win" for r in dec) / len(dec), 3) if dec else None})
    return out


def market_section() -> dict:
    """Everything the markets engine wrote to the repo (picks_latest.json, scorecards.json, change log)."""
    import learning_events as le
    doc = {"latest": None, "scorecards": {}, "changes": [], "notes": []}
    for key, name in (("latest", "picks_latest.json"), ("scorecards", "scorecards.json")):
        p = os.path.join(OUT, "markets", name)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                v = json.load(fh)
            doc[key] = v if key == "latest" else v.get("scorecards", {})
            if key == "scorecards":
                doc["notes"] = v.get("notes", [])
    doc["changes"] = le.read()[-25:]
    return doc


def main() -> None:
    token = os.environ.get("AIRTABLE_TOKEN", "").strip()
    base = os.environ.get("AIRTABLE_BASE_ID", "").strip()
    if not (token and base):
        raise SystemExit("ERROR: AIRTABLE_TOKEN and AIRTABLE_BASE_ID must be set.")
    es.AIRTABLE_BASE = base
    today = central_today()
    games = [r["fields"] | {"_id": r["id"]} for r in fetch(base, token, LEDGER, "{Record Type}='Game'")]
    params = fetch(base, token, PARAMS, "TRUE()")
    graded = [f for f in games if f.get("Grade") in ("Win", "Loss", "Push") and f.get("Sharp-Sheet Tier")]
    upcoming = [f for f in games if (f.get("Date") or "")[:10] >= today.isoformat() and f.get("Home Score") is None]
    picks_up = sorted([f for f in upcoming if f.get("Sharp-Sheet Tier")], key=lambda f: (TIER_RANK.get(f["Sharp-Sheet Tier"], 9), -abs(
        (model_margin(f) or 0) - float(f.get("Vegas Implied Home Margin") or 0))))
    since = (today - dt.timedelta(days=RECENT_DAYS)).isoformat()
    recent = sorted([f for f in graded if (f.get("Date") or "")[:10] >= since], key=lambda f: f.get("Date", ""), reverse=True)

    best = [f for f in picks_up if f["Sharp-Sheet Tier"] != "No Play"]
    tracking = [f for f in picks_up if f["Sharp-Sheet Tier"] == "No Play"]
    state = learning_state(params, graded)
    data = {
        "date": today.isoformat(), "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "upcoming_best": [{"game": f.get("Game"), "date": f.get("Date", "")[:10], "league": f.get("League"), "tier": f["Sharp-Sheet Tier"],
                           "pick": f.get("Recommended Side"), "units": f.get("Sharp-Sheet Suggested Units"), "prob": f.get("Sharp-Sheet Est. Win Prob %"),
                           "adj_edge": f.get("Adj Edge"), "why": drivers_upcoming(f)} for f in best],
        "upcoming_tracking": [{"game": f.get("Game"), "pick": f.get("Recommended Side"), "prob": f.get("Sharp-Sheet Est. Win Prob %"),
                               "why": drivers_upcoming(f)} for f in tracking],
        "recent_closed": [explain_result(f) for f in recent],
        "tiers": tier_table(graded), "edge_buckets": edge_buckets(graded), "learning": state,
        "automatic_changes": automatic_changes(state, graded), "data_gaps": data_gaps(upcoming),
        "overall": {"graded": len(graded), "wins": sum(1 for f in graded if f["Grade"] == "Win"), "losses": sum(1 for f in graded if f["Grade"] == "Loss"),
                    "brier": brier(graded)},
    }
    by_id = {f["_id"]: f for f in games}
    data["splash_vs_model"] = user_vs_model(by_id)
    for r in data["splash_vs_model"]:
        r["model_result"] = _model_result(r, by_id.get(r.get("record_id")))
    data["splash_by_market"] = by_market_summary(data["splash_vs_model"], by_id)
    data["splash_timing"] = timing_table(data["splash_vs_model"])
    data["markets"] = market_section()
    data["narrative_sha256"] = hashlib.sha256(render(data).encode("utf-8")).hexdigest()

    os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
    with open(os.path.join(OUT, "data", f"{today.isoformat()}.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, default=str)
    with open(os.path.join(OUT, "latest.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, default=str)
    # learning log: one row per league per day
    path = os.path.join(OUT, "learning_state.csv")
    cols = ["date", "league", "graded", "graded_with_factor_record", "brier", "sigma", "market_k", "scale_injury", "scale_lookahead",
            "scale_rest", "scale_travel", "scale_revenge", "scale_weather"]
    rows = []
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as fh:
            rows = [r for r in csv.DictReader(fh) if r["date"] != today.isoformat()]
    rows += [{"date": today.isoformat(), **{c: s.get(c, "") for c in cols[1:]}} for s in state]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(OUT, "latest.md"), "w", encoding="utf-8") as fh:
        fh.write(render(data))
    print(f"Report {today}: {len(best)} best bets, {len(tracking)} tracking picks, {len(recent)} recent closed, {len(graded)} graded overall")


def render_markets(m: dict) -> list[str]:
    L = ["", "## Every bet type (paper)", ""]
    latest = m.get("latest")
    if latest:
        rows = []
        for g in latest.get("games", []):
            if g.get("frozen"):
                continue
            for pk in g.get("picks", []):
                if pk["market"] in ("total", "moneyline") and pk["tier"] != "No Play":
                    rows.append([g["game"], pk["market"], pk["selection"], f"{float(pk['prob']):.0%}", pk["tier"], pk["units"]])
        L.append("Lean-or-better totals and moneylines (spreads are in the table above). Every game also has a tracking pick in every market in `intelligence/markets/picks_latest.md`.")
        L.append("")
        L.append(md_table(["Game", "Market", "Pick", "Prob", "Tier", "Units"], rows) if rows else "No Lean-or-better totals or moneylines right now.")
        for lg, cb in (latest.get("combos") or {}).items():
            for kind in ("parlay", "teaser"):
                for c in cb.get(kind, [])[:3]:
                    L.append(f"- {lg} {kind}: " + " + ".join(x["selection"] for x in c["legs"]) +
                             f" | model {c['prob']:.1%}, needs {c['break_even_price']:+g} to break even, edge {c['edge'] * 100:+.1f}%, {c['tier']}")
    else:
        L.append("The markets engine has not produced a pricing file yet.")
    cards = (m.get("scorecards") or {}).get("ALL", {})
    L += ["", "## Results and learning by market", ""]
    if cards:
        L.append(md_table(["Market", "W-L-P", "Win rate", "Units", "Avg CLV", "Brier"],
                          [[k, f"{v['wins']}-{v['losses']}-{v['pushes']}", v["win_rate"], v["units"], v["avg_clv"], v["brier"]] for k, v in cards.items()]))
        L.append("")
        L.append("Tuning only starts at 30 graded picks per league and market; tier tables need 20 per tier.")
    else:
        L.append("No graded results by market yet. Totals, moneylines, legs, teasers and parlays are being logged and will be graded as games finish.")
    for n in m.get("notes", [])[:8]:
        L.append(f"- {n}")
    ch = m.get("changes") or []
    L += ["", "## Automatic changes (change log)", ""]
    L += [f"- {c['date']} {c['league']} {c['market']}: {c['setting']} {c['old']} -> {c['new']} ({c['evidence']}; n={c['sample_size']})" for c in ch[-10:]] or ["No automatic changes logged yet."]
    return L


def render(d: dict) -> str:
    L = [f"# Signal Desk intelligence report, {d['date']}", "",
         "All picks are paper picks. Nothing here is a bet instruction. Generated from Airtable by `intelligence_report.py`.", ""]
    o = d["overall"]
    L += [f"Overall graded picks: {o['wins']}-{o['losses']} (Brier {o['brier']}).", "", "## Upcoming best bets (Lean and above)", ""]
    if d["upcoming_best"]:
        L.append(md_table(["Game", "Date", "Tier", "Pick", "Units", "Win prob", "Adj edge"],
                          [[x["game"], x["date"], x["tier"], x["pick"], x["units"], f"{float(x['prob'] or 0):.1%}", x["adj_edge"]] for x in d["upcoming_best"]]))
        for x in d["upcoming_best"]:
            L.append(f"- {x['game']}: " + "; ".join(x["why"]))
    else:
        L.append("No Lean-or-better picks right now.")
    L += ["", f"Tracking picks (paper, 0u): {len(d['upcoming_tracking'])}. Examples: " +
          "; ".join(f"{x['game']} -> {x['pick']}" for x in d["upcoming_tracking"][:6]), "", f"## Recently closed (last {RECENT_DAYS} days)", ""]
    if d["recent_closed"]:
        L.append(md_table(["Game", "Tier", "Pick", "Result", "Final home margin", "Model", "Line", "CLV"],
                          [[x["game"], x["tier"], x["pick"], x["grade"], x["actual_home_margin"], x["model_margin"], x["line_margin"], x["clv"]] for x in d["recent_closed"][:30]]))
        L.append("")
        L.append("### Why each result happened")
        for x in d["recent_closed"][:30]:
            L.append(f"- {x['game']} ({x['grade']}): " + "; ".join(x["notes"]))
    else:
        L.append("Nothing closed in the window.")
    L += ["", "## How accurate the system has been", "",
          md_table(["League", "Tier", "W", "L", "Hit", "Brier", "Avg CLV", "n"], [[t["league"], t["tier"], t["wins"], t["losses"], t["hit"], t["brier"], t["avg_clv"], t["n"]] for t in d["tiers"]]),
          "", "By size of base edge:", "", md_table(["Edge", "W", "L", "Hit"], [[b["edge"], b["wins"], b["losses"], b["hit"]] for b in d["edge_buckets"]]),
          "", "## What the learner currently believes", ""]
    for s in d["learning"]:
        L.append(f"- {s['league']}: sigma {s['sigma']}, market k {s['market_k']}, scales injury {s['scale_injury']} / look-ahead {s['scale_lookahead']} / rest {s['scale_rest']} / "
                 f"travel {s['scale_travel']} / revenge {s['scale_revenge']} / weather {s['scale_weather']}; graded {s['graded']} ({s['graded_with_factor_record']} with factor records); last calibrated {s['last_calibrated']}")
    L += ["", "## What changes automatically, and how close each change is", "",
          md_table(["League", "Setting", "Now", "Gate", "Progress", "Rule"], [[a["league"], a["setting"], a["now"], a["gate"], a["progress"], a["rule"]] for a in d["automatic_changes"]]),
          "", "## Data gaps right now", ""] + [f"- {g}" for g in d["data_gaps"]]
    L += render_markets(d.get("markets") or {})
    if d["splash_vs_model"]:
        L += ["", "## Your Splash picks vs the model (locked lines)", "",
              "Each pick is graded against the line you locked, not the early-week import. A gap between the two is line movement.", "",
              md_table(["Logged", "Game", "Type", "Pick (locked)", "Early line", "Moved for you", "Model at lock", "Your result", "Model result"],
                       [[r.get("logged_at"), r.get("game"), r.get("ticket_type", "") + "/" + r.get("market", ""),
                         f"{r.get('team')} {r.get('locked_line')}", r.get("imported_line"), r.get("movement_for_you"),
                         f"{r.get('model_side_lock', '')} {r.get('model_tier_lock', '')}".strip(), r["leg_result"],
                         r.get("model_result", "pending")] for r in d["splash_vs_model"]])]
        tk = {}
        for r in d["splash_vs_model"]:
            if r.get("ticket_type") in ("teaser", "parlay") and r.get("ticket_id") not in tk:
                tk[r["ticket_id"]] = r
        if tk:
            L += ["", "Your teasers and parlays: " + "; ".join(f"{r['ticket_type']} {r['logged_at']} -> {r['ticket_result']} (model {r.get('ticket_prob') or 'n/a'} vs break-even {r.get('ticket_break_even') or 'n/a'})" for r in tk.values())]
        if d.get("splash_by_market"):
            L += ["", "By market:", "", md_table(["Market", "Graded", "You W-L", "Model W-L at your line", "Went against model"],
                                              [[m["market"], m["n"], f"{m['you_w']}-{m['you_l']}", f"{m['model_w']}-{m['model_l']}", m["against"]] for m in d["splash_by_market"]])]
        if any(t["n"] for t in d.get("splash_timing", [])):
            L += ["", "Timing (when in the week you locked), small samples are noise until about 30 graded:", "",
                  md_table(["Locked", "Picks", "Avg move for you", "Graded", "Win rate"], [[t["bucket"], t["n"], t["avg_move_for_you"], t["graded"], t["win_rate"]] for t in d["splash_timing"]])]
    L += ["", "## Data points to consider adding", "", "See `signal-desk/intelligence/ROADMAP.md` (kept current by the daily review).", ""]
    return "\n".join(L)


if __name__ == "__main__":
    main()
