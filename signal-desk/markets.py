#!/usr/bin/env python3
"""Every bet on every game: spreads, totals, moneylines, 6-point teasers, parlays, and alternate-line looks.

Primary focus (strongest calibration): spreads, totals, moneylines, parlays. Secondary: teasers and other bets,
which are still priced, ranked and tracked every cycle. ALL OUTPUT IS PAPER. Nothing here writes Airtable.

Pure functions (project, price, grade, combine) are unit-tested. The CLI does the I/O:
  python markets.py run     read ledger + ESPN odds, write intelligence/markets/{lines_log.csv,picks_log.csv,picks_latest.json,picks_latest.md}
  python markets.py grade   grade finished games in picks_log.csv (no odds calls)

Design notes
  * Projections are blended toward the market: expected margin = line + k * (model - line). The model has shown
    little information beyond the line so far (see MODEL.md), k defaults to a weak 0.3 prior and is learned
    from graded results (Model Parameters 'Market Blend K' for margins, market_params.json for totals).
  * Line convention: a team line L is the bet-side number (Alabama -7.5 means L = -7.5); the team wins the bet when
    its margin + L > 0. Splash/ledger 'home margin line' is positive when the home team is favored.
  * Price convention: American odds. Spread/total legs default to -110 when no price is known.
"""
from __future__ import annotations

import csv
import datetime as dt
import itertools
import json
import math
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sigma_learning as sg  # noqa: E402
import situational as sit  # noqa: E402
from statistics import NormalDist

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

OUT = os.path.join(HERE, "intelligence", "markets")
ND = NormalDist()

PRIMARY = ("spread", "total", "moneyline", "parlay", "parlay_leg")
SECONDARY = ("teaser", "teaser_leg", "alt_spread", "other")
MARKETS = ("spread", "total", "moneyline", "teaser_leg", "teaser", "parlay_leg", "parlay", "other")

# --- priors. Every number here is an assumption until market_learning.py has enough graded results. ---------------
DEFAULTS = {
    "NFL": {"sigma_margin": 12.5, "sigma_total": 10.0, "k_margin": 0.3, "k_total": 0.3, "league_team_pts": 22.5,
            "lean_total": 1.5, "strong_total": 3.0, "max_total": 4.5,
            "total_weather_pts": 3.0, "total_qb_out_pts": 1.5, "total_injury_pts": 0.15},
    "NCAAF": {"sigma_margin": 15.0, "sigma_total": 13.0, "k_margin": 0.3, "k_total": 0.3, "league_team_pts": 28.0,
              "lean_total": 2.5, "strong_total": 4.5, "max_total": 6.5,
              "total_weather_pts": 3.5, "total_qb_out_pts": 2.0, "total_injury_pts": 0.2},
}
SHARED = {"lean_ml": 0.03, "strong_ml": 0.06, "max_ml": 0.09,           # moneyline edge in probability points
          "lean_combo": 0.02, "strong_combo": 0.05, "max_combo": 0.08,   # parlay / teaser edge in probability points
          "teaser_leg_min": 0.70, "team_stats_weight": 3.0,
          "units": {"Lean": 0.5, "Strong Play": 1.0, "Max Play": 1.0},  # Strong/Max stay capped at 1.0 paper unit
          "combo_units": {"Lean": 0.25, "Strong Play": 0.5, "Max Play": 0.5},
          "shrink": {"moneyline": 1.0, "total": 1.0, "teaser_leg": 1.0, "parlay_leg": 1.0}}
TEASER_PTS = 6.0
TEASER_PAYOUT = {2: -120, 3: 160, 4: 300}   # reference 6-point teaser prices; the contest's own table decides
PARLAY_LEG_PRICE = -110
KEY_MULT = {  # relative frequency of landing exactly on a number, vs a smooth normal
    "NFL": {3: 1.9, 7: 1.5, 6: 1.25, 10: 1.25, 14: 1.2, 4: 1.1, 1: 1.05, 17: 1.1},
    "NCAAF": {3: 1.35, 7: 1.3, 10: 1.15, 14: 1.15, 6: 1.1, 17: 1.05},
}
# same-game leg correlations (priors)
RHO_SPREAD_ML = 0.9
RHO_MARGIN_TOTAL = 0.05
MC_SAMPLES = 20000


# =============================== price helpers ===============================
def dec_from_american(a: float) -> float:
    return 1 + a / 100 if a > 0 else 1 + 100 / abs(a)


def be_prob(a: float) -> float:
    """Break-even win probability of an American price."""
    return 1 / dec_from_american(a)


def american_from_prob(p: float) -> float:
    p = min(0.999, max(0.001, p))
    return round(-100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


def fair_prob_from_prices(a: float, b: float) -> float:
    """De-vigged probability of side `a` given both sides' prices."""
    pa, pb = be_prob(a), be_prob(b)
    return pa / (pa + pb)


# =============================== parameters ===============================
def load_params(league: str, model_params_fields: dict | None = None, path: str | None = None) -> dict:
    p = {**DEFAULTS.get(league, DEFAULTS["NCAAF"]), **{k: (dict(v) if isinstance(v, dict) else v) for k, v in SHARED.items()}}
    path = path or os.path.join(HERE, "intelligence", "market_params.json")
    try:
        with open(path, encoding="utf-8") as fh:
            saved = json.load(fh).get(league, {})
        for k, v in saved.items():
            if isinstance(v, dict) and isinstance(p.get(k), dict):
                p[k].update(v)
            else:
                p[k] = v
    except (OSError, ValueError):
        pass
    mp = model_params_fields or {}
    if mp.get("Market Blend K") is not None:
        p["k_margin"] = float(mp["Market Blend K"])
    # One sigma source: Model Parameters Sigma (learned by calibrate.py) drives every margin-based market here,
    # the same value picks.py uses. The default above is only the fallback.
    if mp.get("Sigma") is not None:
        p["sigma_margin"] = sg.clean(league, mp["Sigma"])
    p["spread_sigma"] = p["sigma_margin"]
    return p


# =============================== projections ===============================
def model_margin(f: dict) -> float | None:
    try:
        hfa = f.get("HFA")
        if hfa is None:
            hfa = 2.5 if f.get("League") == "NCAAF" else 2.0
        if f.get("Neutral Site"):
            hfa = 0.0 if f.get("HFA") is None else hfa
        return float(f["Home FPI"]) - float(f["Away FPI"]) + float(hfa)
    except (KeyError, TypeError, ValueError):
        return None


def _detail(f: dict) -> dict:
    try:
        return json.loads(f.get("Factor Detail") or "") or {}
    except ValueError:
        return {}


def scoring_expectation(f: dict, p: dict) -> tuple[float | None, str]:
    """Team-scoring total from season points for/against, shrunk toward the league mean. None when no stats."""
    try:
        sd = json.loads(f.get("Scoring Detail") or "")
        h, a = sd["home"], sd["away"]
    except (ValueError, KeyError, TypeError):
        return None, "no scoring stats"
    mean, w = p["league_team_pts"], p["team_stats_weight"]

    def shr(v, n):
        n = float(n or 0)
        return (v * n + mean * w) / (n + w) if v is not None else mean
    home_exp = (shr(h.get("pf"), h.get("n")) + shr(a.get("pa"), a.get("n"))) / 2
    away_exp = (shr(a.get("pf"), a.get("n")) + shr(h.get("pa"), h.get("n"))) / 2
    return home_exp + away_exp, f"home {home_exp:.1f} + away {away_exp:.1f} from season scoring (n {h.get('n')}/{a.get('n')})"


def total_factor_points(f: dict, p: dict) -> tuple[float, list[str]]:
    """Points added to the projected total from weather, quarterback status and injuries (negative lowers the total)."""
    pts, why = 0.0, []
    note = f.get("Weather Note") or ""
    m = re.search(r"sev=([0-9.]+)", note)
    if m and float(m.group(1)) > 0:
        w = -float(m.group(1)) * p["total_weather_pts"]
        pts += w
        why.append(f"weather {w:+.1f}")
    qb = f.get("QB Starter Note") or ""
    priced = sit.qb_priced(qb)  # absences the line already reflects add nothing
    for side in ("HOME", "AWAY"):
        if side.lower() in priced:
            continue
        if f"{side} QB OUT" in qb:
            pts -= p["total_qb_out_pts"]
            why.append(f"{side.lower()} QB out {-p['total_qb_out_pts']:+.1f}")
        elif f"{side} QB QUESTIONABLE" in qb:
            pts -= 0.25 * p["total_qb_out_pts"]
            why.append(f"{side.lower()} QB questionable {-0.25 * p['total_qb_out_pts']:+.1f}")
    d = _detail(f)
    inj = float(d.get("home_inj_pts") or 0) + float(d.get("away_inj_pts") or 0)
    if inj:
        w = -inj * p["total_injury_pts"]
        pts += w
        why.append(f"injuries {w:+.1f}")
    return pts, why


def margin_distribution(mean: float, sigma: float, league: str) -> dict[int, float]:
    """Probability of each integer final margin: a normal reshaped by key-number frequencies."""
    mult = KEY_MULT.get(league, {})
    w = {x: math.exp(-0.5 * ((x - mean) / sigma) ** 2) * mult.get(abs(x), 1.0) for x in range(-70, 71)}
    s = sum(w.values())
    return {x: v / s for x, v in w.items()}


def cover(mean_team: float, line: float, sigma: float, league: str) -> tuple[float, float]:
    """(win, push) probability that a team with expected margin `mean_team` covers bet line `line`."""
    dist = margin_distribution(mean_team, sigma, league)
    win = sum(v for x, v in dist.items() if x + line > 0)
    push = sum(v for x, v in dist.items() if abs(x + line) < 1e-9)
    return win, push


def tier_for(edge: float, lean: float, strong: float, mx: float) -> str:
    return "Max Play" if edge >= mx else "Strong Play" if edge >= strong else "Lean" if edge >= lean else "No Play"


def qb_new_cap(tier: str, f: dict) -> str:
    """Same rule as picks.py: a new quarterback absence keeps the pick at Lean or below."""
    if tier in ("Strong Play", "Max Play") and (_detail(f).get("qb_out_new") or {}) and \
            os.environ.get("QB_OUT_NEW_CAP", "lean").strip().lower() != "off":
        return "Lean"
    return tier


def project_game(f: dict, odds: dict | None, p: dict, factor_live: bool = False) -> dict:
    """All projections for one ledger game. `odds` is the current market (see parse_odds) or None."""
    league = f.get("League") or "NCAAF"
    m = model_margin(f)
    d = _detail(f)
    adj = f.get("Adj Model Home Margin")
    use_adj = factor_live and adj is not None
    M = float(adj) if use_adj else m
    line = None
    if odds and odds.get("home_margin_line") is not None:
        line = float(odds["home_margin_line"])
    elif f.get("Vegas Implied Home Margin") is not None:
        line = float(f["Vegas Implied Home Margin"])
    elif f.get("ESPN Spread (Home)") is not None:
        line = -float(f["ESPN Spread (Home)"])
    total_line = None
    if odds and odds.get("total") is not None:
        total_line = float(odds["total"])
    elif f.get("Over/Under Line") is not None:
        total_line = float(f["Over/Under Line"])
    elif f.get("ESPN Total") is not None:
        total_line = float(f["ESPN Total"])
    out = {"league": league, "model_margin": m, "adj_margin": None if adj is None else float(adj), "used_adjusted": use_adj,
           "line": line, "total_line": total_line, "factors": [], "factor_json": {}}
    if M is not None and line is not None:
        k = p["k_margin"]
        out["blend_margin"] = line + k * (M - line)
    elif M is not None:
        out["blend_margin"] = M
    # totals
    team_total, tw = scoring_expectation(f, p)
    out["team_total"], out["team_total_why"] = team_total, tw
    if total_line is not None:
        base = total_line + p["k_total"] * ((team_total if team_total is not None else total_line) - total_line)
        fpts, fwhy = total_factor_points(f, p)
        out["total_factor_pts"], out["total_factor_why"] = fpts, fwhy
        out["proj_total"] = base + (fpts if factor_live else 0.0)
        out["proj_total_shadow"] = base + fpts
    # factor text (all markets)
    parts = (d.get("situ_parts") or {})
    for k_, label in (("rest", "rest"), ("travel", "travel"), ("revenge", "revenge"), ("lookahead", "look-ahead"), ("weather", "weather")):
        if parts.get(k_):
            out["factors"].append(f"{label} {parts[k_]:+.1f} to home")
    if d.get("home_inj_pts") or d.get("away_inj_pts"):
        out["factors"].append(f"injuries: home -{d.get('home_inj_pts', 0)}, away -{d.get('away_inj_pts', 0)}")
    if f.get("QB Starter Note"):
        out["factors"].append("QB: " + f["QB Starter Note"])
    if f.get("Weather Note"):
        out["factors"].append("weather: " + f["Weather Note"])
    out["factor_json"] = {"inj_home": d.get("home_inj_pts"), "inj_away": d.get("away_inj_pts"), **{k: v for k, v in parts.items()}}
    return out


def ml_prices(odds: dict | None, line: float | None, sigma: float) -> tuple[float, float, bool]:
    """(home price, away price, estimated). Uses the book's moneylines; else derives them from the line with 4.5% vig."""
    if odds and odds.get("ml_home") is not None and odds.get("ml_away") is not None:
        return float(odds["ml_home"]), float(odds["ml_away"]), False
    if line is None:
        return -110.0, -110.0, True
    ph = ND.cdf(line / sigma)
    ph_v, pa_v = min(0.97, ph * 1.0225), min(0.97, (1 - ph) * 1.0225)
    return american_from_prob(ph_v), american_from_prob(pa_v), True


# =============================== single-market picks ===============================
def _units(tier: str, p: dict, combo: bool = False) -> float:
    return 0.0 if tier == "No Play" else float((p["combo_units"] if combo else p["units"])[tier])


def shrink_prob(prob: float, market: str, p: dict) -> float:
    s = p["shrink"].get(market, 1.0)
    return 0.5 + s * (prob - 0.5)


def game_sigma(f: dict, proj: dict, p: dict) -> float:
    """League sigma (one source with picks.py) times learned context multipliers for this game."""
    try:
        detail = json.loads(f.get("Factor Detail") or "")
    except (TypeError, ValueError):
        detail = None
    segs = ((sg.read_params().get("sigma") or {}).get(proj.get("league") or f.get("League") or "") or {}).get("segments")
    return sg.sigma_for(p["sigma_margin"], proj.get("line"), detail, segs)[0]


def moneyline_pick(f: dict, proj: dict, odds: dict | None, p: dict) -> dict | None:
    M = proj.get("blend_margin")
    if M is None:
        return None
    sigma = game_sigma(f, proj, p)
    ph = shrink_prob(ND.cdf(M / sigma), "moneyline", p)
    hp, ap, est = ml_prices(odds, proj.get("line"), sigma)
    eh, ea = ph - be_prob(hp), (1 - ph) - be_prob(ap)
    home = eh >= ea
    edge, prob, price = (eh, ph, hp) if home else (ea, 1 - ph, ap)
    tier = qb_new_cap(tier_for(edge, p["lean_ml"], p["strong_ml"], p["max_ml"]), f)
    team = f.get("Home Team") if home else f.get("Away Team")
    return {"market": "moneyline", "side": "home" if home else "away", "team": team, "line": 0.0, "price": price,
            "price_estimated": est, "proj": round(M, 2), "prob": round(prob, 4), "edge": round(edge, 4), "edge_unit": "prob",
            "tier": tier, "units": _units(tier, p),
            "selection": f"{team} ML {price:+g}" + (" (price estimated from the line)" if est else "")}


def total_pick(f: dict, proj: dict, odds: dict | None, p: dict) -> dict | None:
    T, L = proj.get("proj_total"), proj.get("total_line")
    if T is None or L is None:
        return None
    sigma = p["sigma_total"]
    over = T >= L
    prob = shrink_prob(ND.cdf((T - L) / sigma) if over else ND.cdf((L - T) / sigma), "total", p)
    edge = abs(T - L)
    tier = qb_new_cap(tier_for(edge, p["lean_total"], p["strong_total"], p["max_total"]), f)
    price = PARLAY_LEG_PRICE
    if odds:
        price = odds.get("over_odds" if over else "under_odds") or price
    return {"market": "total", "side": "over" if over else "under", "line": L, "price": float(price), "proj": round(T, 2),
            "prob": round(prob, 4), "edge": round(edge, 2), "edge_unit": "pts", "tier": tier, "units": _units(tier, p),
            "selection": f"{'Over' if over else 'Under'} {L:g}"}


def spread_pick_from_ledger(f: dict, proj: dict, odds: dict | None, p: dict) -> dict | None:
    """The spread pick comes from picks.py (single source of truth); here it is only normalised for tracking."""
    import close_grade as cg
    pk = cg.parse_pick(f.get("Recommended Side") or "")
    if not f.get("Sharp-Sheet Tier") or not pk or pk[0] != "spread":
        return None
    ish = cg.side_is_home(pk[1], f.get("Home Team", ""), f.get("Away Team", ""))
    if ish is None:
        return None
    price = -110.0
    if odds:
        price = odds.get("spread_odds_home" if ish else "spread_odds_away") or price
    return {"market": "spread", "side": "home" if ish else "away", "team": pk[1], "line": float(pk[2]), "price": float(price),
            "proj": proj.get("model_margin"), "prob": float(f.get("Sharp-Sheet Est. Win Prob %") or 0.5),
            "edge": f.get("Adj Edge") if f.get("Adj Edge") is not None else f.get("Edge"), "edge_unit": "pts",
            "tier": f.get("Sharp-Sheet Tier"), "units": float(f.get("Sharp-Sheet Suggested Units") or 0.0),
            "selection": f.get("Recommended Side")}


def teaser_leg(f: dict, proj: dict, kind: str, p: dict, team_side: str | None = None, over: bool | None = None) -> dict | None:
    """Best 6-point teased leg for the game's spread or total. Returns None when no projection exists."""
    league = proj["league"]
    if kind == "spread":
        M, line = proj.get("blend_margin"), proj.get("line")
        if M is None or line is None:
            return None
        sigma = game_sigma(f, proj, p)
        options = []
        for home in ((team_side == "home"),) if team_side else (True, False):
            mean_team = M if home else -M
            base = -line if home else line     # bet-side base line from the market
            tl = base + TEASER_PTS
            win, push = cover(mean_team, tl, sigma, league)
            options.append((win, push, home, base, tl))
        win, push, home, base, tl = max(options)
        win = shrink_prob(win, "teaser_leg", p)
        team = f.get("Home Team") if home else f.get("Away Team")
        crossed = [n for n in (3, 7) if _crosses(base, tl, n)] if league == "NFL" else [n for n in (3, 7) if _crosses(base, tl, n)]
        return {"market": "teaser_leg", "kind": "spread", "side": "home" if home else "away", "team": team, "base_line": base,
                "line": tl, "price": 0.0, "prob": round(win, 4), "push": round(push, 4), "crosses": crossed,
                "selection": f"{team} {base:+g} -> {tl:+g}" + (f" (crosses {' and '.join(map(str, crossed))})" if crossed else "")}
    T, L = proj.get("proj_total"), proj.get("total_line")
    if T is None or L is None:
        return None
    sigma = p["sigma_total"]
    res = []
    for ov in ((over,) if over is not None else (True, False)):
        tl = L - TEASER_PTS if ov else L + TEASER_PTS
        pr = ND.cdf((T - tl) / sigma) if ov else ND.cdf((tl - T) / sigma)
        res.append((pr, ov, tl))
    pr, ov, tl = max(res)
    pr = shrink_prob(pr, "teaser_leg", p)
    return {"market": "teaser_leg", "kind": "total", "side": "over" if ov else "under", "base_line": L, "line": tl, "price": 0.0,
            "prob": round(pr, 4), "push": 0.0, "crosses": [], "selection": f"{'Over' if ov else 'Under'} {L:g} -> {tl:g}"}


def _crosses(base: float, teased: float, n: int) -> bool:
    lo, hi = sorted((base, teased))
    return any(lo < v <= hi for v in (-n, n))


# =============================== combinations ===============================
def _rho(a: dict, b: dict) -> float:
    if a["game_id"] != b["game_id"]:
        return 0.0
    am, bm = a["market_kind"] in ("spread", "moneyline"), b["market_kind"] in ("spread", "moneyline")
    if am and bm:
        return RHO_SPREAD_ML if a["side"] == b["side"] else -RHO_SPREAD_ML
    if a["market_kind"] == "total" and b["market_kind"] == "total":
        return 1.0 if a["side"] == b["side"] else -1.0
    # margin leg with a total leg: favourite-and-over / underdog-and-under lean together
    m, t = (a, b) if am else (b, a)
    fav = 1 if m.get("pro_favorite") else -1
    d = 1 if t["side"] == "over" else -1
    return RHO_MARGIN_TOTAL * fav * d


def joint_prob(legs: list[dict], samples: int = MC_SAMPLES, seed: int = 11) -> float:
    """Probability all legs win, Gaussian copula with same-game correlations. Independent games are exact products."""
    probs = [min(0.999, max(0.001, l["prob"])) for l in legs]
    n = len(legs)
    R = [[1.0 if i == j else _rho(legs[i], legs[j]) for j in range(n)] for i in range(n)]
    if all(R[i][j] == 0 for i in range(n) for j in range(n) if i != j):
        return math.prod(probs)
    L = _cholesky(R)
    if L is None:
        return math.prod(probs)
    z_cut = [ND.inv_cdf(p_) for p_ in probs]
    rnd, hit = random.Random(seed), 0
    for _ in range(samples):
        e = [rnd.gauss(0, 1) for _ in range(n)]
        if all(sum(L[i][k] * e[k] for k in range(i + 1)) < z_cut[i] for i in range(n)):
            hit += 1
    return hit / samples


def _cholesky(a: list[list[float]]) -> list[list[float]] | None:
    n = len(a)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                v = a[i][i] - s
                if v <= 1e-9:
                    return None
                L[i][j] = math.sqrt(v)
            else:
                L[i][j] = (a[i][j] - s) / L[j][j]
    return L


def combo(legs: list[dict], kind: str, p: dict) -> dict:
    """Price a parlay or teaser from legs {game_id, market_kind, side, prob, price|None, ...}."""
    n = len(legs)
    jp = joint_prob(legs)
    if kind == "teaser":
        price = float(TEASER_PAYOUT.get(n, TEASER_PAYOUT[max(TEASER_PAYOUT)]))
        dec = dec_from_american(price)
    else:
        dec = math.prod(dec_from_american(l.get("price") or PARLAY_LEG_PRICE) for l in legs)
        price = american_from_prob(1 / dec)
    be = 1 / dec
    edge = jp - be
    tier = tier_for(edge, p["lean_combo"], p["strong_combo"], p["max_combo"])
    correlated = any(legs[i]["game_id"] == legs[j]["game_id"] for i in range(n) for j in range(i + 1, n))
    return {"market": kind, "legs": legs, "n_legs": n, "prob": round(jp, 4), "price": price, "break_even_prob": round(be, 4),
            "break_even_price": american_from_prob(be), "edge": round(edge, 4), "edge_unit": "prob", "tier": tier,
            "units": _units(tier, p, combo=True), "same_game": correlated}


def build_combos(singles: list[dict], teaser_legs: list[dict], p: dict, max_legs: int = 3, top: int = 5) -> dict:
    """Best parlays from Lean-or-better legs and best 6-point teasers from the strongest teased legs."""
    out = {"parlay": [], "teaser": []}
    pool = [s for s in singles if s["tier"] != "No Play" and s["market"] in ("spread", "total", "moneyline")]
    for n in range(2, max_legs + 1):
        for legs in itertools.combinations(pool, n):
            ids = [l["game_id"] for l in legs]
            kinds = [(l["game_id"], l["market"]) for l in legs]
            if len(set(kinds)) < n:
                continue
            if any(ids.count(i) > 1 and sum(1 for l in legs if l["game_id"] == i and l["market"] in ("spread", "moneyline")) > 1 for i in set(ids)):
                continue   # spread + moneyline on the same game is one bet counted twice
            cl = [{"game_id": l["game_id"], "market_kind": l["market"], "side": l["side"], "prob": l["prob"],
                   "price": l.get("price"), "pro_favorite": l.get("pro_favorite", False), "selection": l["selection"], "game": l["game"],
                   "line": l.get("line"), "grade_market": l["market"]} for l in legs]
            out["parlay"].append(combo(cl, "parlay", p))
    tl = sorted([t for t in teaser_legs if t["prob"] >= p["teaser_leg_min"]], key=lambda t: -t["prob"])[:7]
    for n in (2, 3):
        for legs in itertools.combinations(tl, n):
            if len({l["game_id"] for l in legs}) < n:
                continue
            cl = [{"game_id": l["game_id"], "market_kind": "total" if l["kind"] == "total" else "spread", "side": l["side"],
                   "prob": l["prob"], "price": None, "pro_favorite": False, "selection": l["selection"], "game": l["game"],
                   "line": l["line"], "grade_market": "teaser_leg", "kind": l["kind"], "base_line": l["base_line"]} for l in legs]
            out["teaser"].append(combo(cl, "teaser", p))
    for k in out:
        out[k] = sorted(out[k], key=lambda c: -c["edge"])[:top]
    return out


# =============================== grading ===============================
def grade_leg(market: str, side: str, line: float, home_score: float, away_score: float, kind: str | None = None) -> str:
    """Win/Loss/Push for one leg. `line` is the bet-side line (team line, or the total)."""
    hs, as_ = float(home_score), float(away_score)
    if market == "moneyline":
        if hs == as_:
            return "Push"
        return "Win" if (hs > as_) == (side == "home") else "Loss"
    if market == "total" or (market == "teaser_leg" and kind == "total") or kind == "total":
        pts = hs + as_
        if pts == line:
            return "Push"
        return "Win" if (pts > line) == (side == "over") else "Loss"
    margin = (hs - as_) if side == "home" else (as_ - hs)
    adj = margin + line
    return "Win" if adj > 0 else ("Loss" if adj < 0 else "Push")


def grade_combo(results: list[str]) -> str:
    if any(r == "pending" for r in results):
        return "pending"
    if any(r == "Loss" for r in results):
        return "Loss"
    live = [r for r in results if r == "Win"]
    return "Win" if live else "Push"


def units_won(result: str, units: float, price: float) -> float:
    if result == "Win":
        return round(units * (dec_from_american(price) - 1), 3)
    return round(-units, 3) if result == "Loss" else 0.0


def clv_points(market: str, side: str, pick_line: float, close_line: float | None) -> float | None:
    """Positive means the bettor got a better number than the close."""
    if close_line is None:
        return None
    if market == "total" or side in ("over", "under"):
        return round((close_line - pick_line) if side == "over" else (pick_line - close_line), 2)
    return round(pick_line - close_line, 2)


# =============================== odds I/O ===============================
CORE = "https://sports.core.api.espn.com/v2/sports/football/leagues/{lg}/events/{eid}/competitions/{eid}/odds"


def parse_odds(payload: dict) -> dict | None:
    """Pick the pre-game book from ESPN's core odds list (the 'Live Odds' item marks a game in progress)."""
    items = payload.get("items") or []
    live = any("live" in ((i.get("provider") or {}).get("name", "")).lower() for i in items)
    pre = [i for i in items if "live" not in ((i.get("provider") or {}).get("name", "")).lower()]
    if not pre:
        return None
    o = pre[0]
    home, away = o.get("homeTeamOdds") or {}, o.get("awayTeamOdds") or {}
    spread = o.get("spread")
    margin_line = None
    if spread is not None and home.get("favorite") is not None:
        margin_line = abs(float(spread)) if home.get("favorite") else -abs(float(spread))
        if spread == 0:
            margin_line = 0.0
    open_ = (home.get("open") or {})
    return {"provider": (o.get("provider") or {}).get("name"), "in_progress": live,
            "home_margin_line": margin_line, "total": o.get("overUnder"),
            "ml_home": home.get("moneyLine"), "ml_away": away.get("moneyLine"),
            "spread_odds_home": home.get("spreadOdds"), "spread_odds_away": away.get("spreadOdds"),
            "over_odds": o.get("overOdds"), "under_odds": o.get("underOdds"),
            "open_margin_line": _open_margin(home, away)}


def _open_margin(home: dict, away: dict) -> float | None:
    try:
        v = float(((home.get("open") or {}).get("pointSpread") or {}).get("american"))
        return -v   # home spread -3.5 -> home margin line +3.5
    except (TypeError, ValueError):
        return None


LINE_COLS = ["ts", "record_id", "event_id", "league", "game", "date", "provider", "home_margin_line", "total", "ml_home", "ml_away",
             "spread_odds_home", "spread_odds_away", "over_odds", "under_odds", "open_margin_line"]
PICK_COLS = ["pick_id", "first_seen", "last_updated", "frozen", "priority", "market", "league", "game_ids", "game", "date", "selection",
             "side", "line", "price", "proj", "prob", "edge", "edge_unit", "tier", "units", "factors", "legs_json",
             "result", "units_won", "close_line", "clv", "graded_at"]


def read_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: str, cols: list[str], rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def log_lines(rows: list[dict], new: list[dict]) -> list[dict]:
    """Append a line row only when the market moved for that game (keeps the log small)."""
    last = {}
    for r in rows:
        last[r["record_id"]] = r
    keys = ("home_margin_line", "total", "ml_home", "ml_away", "spread_odds_home", "spread_odds_away", "over_odds", "under_odds")
    for n in new:
        prev = last.get(n["record_id"])
        if prev is None or any(str(prev.get(k) or "") != str(n.get(k) if n.get(k) is not None else "") for k in keys):
            rows.append({k: ("" if n.get(k) is None else n.get(k)) for k in LINE_COLS})
            last[n["record_id"]] = rows[-1]
    return rows


def last_lines(rows: list[dict]) -> dict:
    out = {}
    for r in rows:
        out[r["record_id"]] = r
    return out


def _num(v):
    try:
        return None if v in (None, "") else float(v)
    except ValueError:
        return None


def pick_id(market: str, game_ids: list[str], selection: str) -> str:
    return f"{market}:{'+'.join(game_ids)}:{re.sub(r'[^A-Za-z0-9.+-]+', '_', selection)[:60]}"


def upsert_pick(rows: dict, pick: dict, now: str) -> None:
    """Insert or refresh a pick; frozen picks (game started) keep their last pre-game numbers."""
    cur = rows.get(pick["pick_id"])
    if cur and str(cur.get("frozen")) == "1":
        return
    base = {**(cur or {"first_seen": now}), **pick, "last_updated": now}
    rows[pick["pick_id"]] = base


# =============================== run / grade ===============================
def _league_slug(league: str) -> str:
    return "nfl" if league == "NFL" else "college-football"


def fetch_odds(f: dict) -> dict | None:
    import espn_sync as es
    eid = f.get("ESPN Event ID")
    if not eid:
        return None
    try:
        return parse_odds(json.loads(es.http_get(CORE.format(lg=_league_slug(f.get("League")), eid=eid))))
    except Exception as exc:  # noqa: BLE001
        es.warn(f"{f.get('Game')}: odds fetch failed: {exc}")
        return None


def _fetch_ledger():
    import intelligence_report as ir
    import espn_sync as es
    token = os.environ.get("AIRTABLE_TOKEN", "").strip()
    base = os.environ.get("AIRTABLE_BASE_ID", "").strip() or os.environ.get("SIGNAL_DESK_BASE_ID", "").strip()
    if not (token and base):
        raise SystemExit("ERROR: AIRTABLE_TOKEN and AIRTABLE_BASE_ID must be set.")
    es.AIRTABLE_BASE = base
    games = [r["fields"] | {"_id": r["id"]} for r in ir.fetch(base, token, ir.LEDGER, "{Record Type}='Game'")]
    params = {}
    for r in ir.fetch(base, token, ir.PARAMS, "TRUE()"):
        fl_ = r["fields"]
        params[fl_.get("League")] = fl_
    return games, params, ir.central_today()


def game_label(f: dict) -> str:
    return f.get("Game") or f"{f.get('Away Team')} @ {f.get('Home Team')}"


def run(games: list[dict], mparams: dict, today: dt.date, odds_lookup, lines_rows: list[dict], picks_rows: dict,
        factor_live: bool, now: str) -> dict:
    """One full cycle over the ledger. `odds_lookup(f)` returns parsed odds or None. Returns the latest-picks document."""
    horizon = (today + dt.timedelta(days=7)).isoformat()
    window = [f for f in games if today.isoformat() <= (f.get("Date") or "")[:10] <= horizon and f.get("Home Team")]
    new_lines, doc_games = [], []
    singles_by_league: dict[str, list[dict]] = {}
    tlegs_by_league: dict[str, list[dict]] = {}
    seen_combo_ids: set[str] = set()
    for f in window:
        league = f.get("League") or "NCAAF"
        p = load_params(league, mparams.get(league), None)
        started = f.get("Home Score") is not None
        odds = None if started else odds_lookup(f)
        if odds is not None:
            new_lines.append({**odds, "ts": now, "record_id": f["_id"], "event_id": f.get("ESPN Event ID"), "league": league,
                              "game": game_label(f), "date": (f.get("Date") or "")[:10]})
        frozen = started or bool(odds and odds.get("in_progress"))
        proj = project_game(f, odds, p, factor_live)
        gid, label, date = f["_id"], game_label(f), (f.get("Date") or "")[:10]
        picks = []
        for pk in (spread_pick_from_ledger(f, proj, odds, p), total_pick(f, proj, odds, p), moneyline_pick(f, proj, odds, p)):
            if pk:
                pk["game_id"], pk["game"], pk["priority"] = gid, label, "primary"
                line = proj.get("line")
                pk["pro_favorite"] = bool(line is not None and ((pk.get("side") == "home") == (line >= 0))) if pk["market"] != "total" else False
                picks.append(pk)
        legs = []
        for kind in ("spread", "total"):
            tl = teaser_leg(f, proj, kind, p)
            if tl:
                tl.update({"game_id": gid, "game": label, "priority": "secondary", "tier": "No Play", "units": 0.0})
                legs.append(tl)
        # alternate spreads: probabilities only (no prices are available), logged at secondary priority
        alt = []
        if proj.get("blend_margin") is not None and proj.get("line") is not None:
            for shift in (-3, 3):
                for home in (True, False):
                    base = (-proj["line"] if home else proj["line"]) + shift
                    win, push = cover(proj["blend_margin"] if home else -proj["blend_margin"], base, game_sigma(f, proj, p), league)
                    alt.append({"team": f.get("Home Team") if home else f.get("Away Team"), "line": base, "prob": round(win, 4)})
        doc_games.append({"game_id": gid, "game": label, "league": league, "date": date, "frozen": frozen, "line": proj.get("line"),
                          "total_line": proj.get("total_line"), "model_margin": proj.get("model_margin"), "blend_margin": proj.get("blend_margin"),
                          "proj_total": proj.get("proj_total"), "factors": proj["factors"], "total_factor_why": proj.get("total_factor_why"),
                          "picks": picks, "teaser_legs": legs, "alt_spreads": alt})
        if not frozen:
            singles_by_league.setdefault(league, []).extend(picks)
            tlegs_by_league.setdefault(league, []).extend(legs)
        fac = "; ".join(proj["factors"])
        for pk in picks:
            upsert_pick(picks_rows, {"pick_id": f"{pk['market']}:{gid}", "frozen": "", "priority": pk["priority"], "market": pk["market"],
                                     "league": league, "game_ids": gid, "game": label, "date": date, "selection": pk["selection"],
                                     "side": pk.get("side"), "line": pk.get("line"), "price": pk.get("price"), "proj": pk.get("proj"),
                                     "prob": pk.get("prob"), "edge": pk.get("edge"), "edge_unit": pk.get("edge_unit"), "tier": pk["tier"],
                                     "units": pk["units"], "factors": fac, "legs_json": ""}, now) if not frozen else None
        for tl in legs:
            upsert_pick(picks_rows, {"pick_id": f"teaser_leg:{gid}:{tl['kind']}", "frozen": "", "priority": "secondary", "market": "teaser_leg",
                                     "league": league, "game_ids": gid, "game": label, "date": date, "selection": tl["selection"],
                                     "side": tl["side"], "line": tl["line"], "price": "", "proj": "", "prob": tl["prob"], "edge": "",
                                     "edge_unit": "", "tier": "No Play", "units": 0.0, "factors": fac,
                                     "legs_json": json.dumps({"kind": tl["kind"], "base_line": tl["base_line"], "crosses": tl["crosses"]})}, now) if not frozen else None
    combos_doc = {}
    for league, singles in singles_by_league.items():
        p = load_params(league, mparams.get(league), None)
        cb = build_combos(singles, tlegs_by_league.get(league, []), p)
        combos_doc[league] = cb
        for kind in ("parlay", "teaser"):
            for c in cb[kind]:
                ids = sorted(f"{l['game_id']}:{l['grade_market']}:{l['side']}" for l in c["legs"])
                pid = f"{kind}:{league}:" + "|".join(ids)
                seen_combo_ids.add(pid)
                upsert_pick(picks_rows, {"pick_id": pid, "frozen": "", "priority": "primary" if kind == "parlay" else "secondary", "market": kind,
                                         "league": league, "game_ids": "+".join(sorted({l["game_id"] for l in c["legs"]})),
                                         "game": " | ".join(l["game"] for l in c["legs"]), "date": min(
                                             (g["date"] for g in doc_games if g["game_id"] in {l["game_id"] for l in c["legs"]}), default=""),
                                         "selection": " + ".join(l["selection"] for l in c["legs"]), "side": "", "line": "",
                                         "price": c["price"], "proj": "", "prob": c["prob"], "edge": c["edge"], "edge_unit": "prob",
                                         "tier": c["tier"], "units": c["units"], "factors": f"break-even {c['break_even_prob']:.3f}; same-game {c['same_game']}",
                                         "legs_json": json.dumps(c["legs"])}, now)
    # combos that dropped out of the top list before kickoff are retired, not graded
    started_ids = {g["game_id"] for g in doc_games if g["frozen"]}
    for pid, r in picks_rows.items():
        if r["market"] in ("parlay", "teaser") and str(r.get("frozen")) != "1" and not r.get("result"):
            gids = set((r.get("game_ids") or "").split("+"))
            if pid not in seen_combo_ids and not (gids & started_ids):
                r["frozen"], r["result"] = "1", "retired"
    return {"generated_at": now, "date": today.isoformat(), "games": doc_games, "combos": combos_doc, "new_lines": new_lines}


def freeze_started(games: list[dict], picks_rows: dict, lines_rows: list[dict]) -> None:
    """Freeze every pick whose game has a score or has moved to live odds (frozen picks keep their last pregame numbers)."""
    done = {g["_id"] for g in games if g.get("Home Score") is not None}
    for r in picks_rows.values():
        if str(r.get("frozen")) == "1":
            continue
        gids = set((r.get("game_ids") or "").split("+"))
        if gids & done:
            r["frozen"] = "1"


def grade_picks(games: list[dict], picks_rows: dict, lines_rows: list[dict], now: str) -> int:
    by_id = {g["_id"]: g for g in games}
    last = last_lines(lines_rows)
    n = 0
    for r in picks_rows.values():
        if r.get("result") in ("Win", "Loss", "Push", "retired"):
            continue
        gids = [g for g in (r.get("game_ids") or "").split("+") if g]
        if not gids or any(by_id.get(g, {}).get("Home Score") is None for g in gids):
            continue
        m = r["market"]
        price = _num(r.get("price")) or PARLAY_LEG_PRICE
        if m in ("spread", "total", "moneyline", "teaser_leg"):
            g = by_id[gids[0]]
            kind = json.loads(r["legs_json"]).get("kind") if m == "teaser_leg" and r.get("legs_json") else None
            res = grade_leg(m, r.get("side"), _num(r.get("line")) or 0.0, g["Home Score"], g["Away Score"], kind)
            r["result"] = res
            r["units_won"] = units_won(res, _num(r.get("units")) or 0.0, price) if m != "teaser_leg" else ""
            if m in ("spread", "total"):
                ll = last.get(gids[0])
                close = None
                if ll:
                    ml_, tot = _num(ll.get("home_margin_line")), _num(ll.get("total"))
                    if m == "total":
                        close = tot
                    elif ml_ is not None:
                        close = -ml_ if r.get("side") == "home" else ml_
                if close is not None:
                    r["close_line"], r["clv"] = close, clv_points(m, r.get("side"), _num(r.get("line")), close)
        elif m in ("parlay", "teaser"):
            legs = json.loads(r.get("legs_json") or "[]")
            results = []
            for l in legs:
                g = by_id[l["game_id"]]
                l["result"] = grade_leg(l["grade_market"], l["side"], float(l["line"] or 0), g["Home Score"], g["Away Score"], l.get("kind"))
                results.append(l["result"])
            r["legs_json"] = json.dumps(legs)
            res = grade_combo(results)
            r["result"] = res
            wins = [x for x in results if x == "Win"]
            if m == "teaser" and res == "Win" and len(wins) < len(results):
                r["units_won"] = units_won(res, _num(r.get("units")) or 0.0, TEASER_PAYOUT.get(len(wins), price))
            elif m == "parlay" and res == "Win" and len(wins) < len(results):
                dec = math.prod(dec_from_american(l.get("price") or PARLAY_LEG_PRICE) for l in legs if l["result"] == "Win")
                r["units_won"] = round((_num(r.get("units")) or 0.0) * (dec - 1), 3)
            else:
                r["units_won"] = units_won(res, _num(r.get("units")) or 0.0, price)
        else:
            continue
        r["frozen"], r["graded_at"] = "1", now
        n += 1
    return n


def render_md(doc: dict) -> str:
    L = [f"# Signal Desk: every bet, every game ({doc['date']})", "",
         "All picks are paper picks. Primary markets: spreads, totals, moneylines, parlays. Teasers and other bets are secondary and tracked.", ""]
    for league in sorted({g["league"] for g in doc["games"]}):
        L += [f"## {league}", "", "| Game | Market | Pick | Prob | Edge | Tier | Units |", "|---|---|---|---|---|---|---|"]
        for g in doc["games"]:
            if g["league"] != league or g["frozen"]:
                continue
            for pk in g["picks"]:
                e = pk.get("edge")
                es_ = "" if e is None else (f"{e:+.1f} pts" if pk.get("edge_unit") == "pts" else f"{e * 100:+.1f}%")
                L.append(f"| {g['game']} | {pk['market']} | {pk['selection']} | {float(pk['prob']) * 100:.0f}% | {es_} | {pk['tier']} | {pk['units']:g} |")
        cb = doc["combos"].get(league) or {}
        for kind, title in (("parlay", "Best parlays"), ("teaser", "Best 6-point teasers")):
            if cb.get(kind):
                L += ["", f"### {league} {title}", ""]
                for c in cb[kind]:
                    L.append(f"- {' + '.join(l['selection'] for l in c['legs'])}: model {c['prob'] * 100:.1f}%, needs {c['break_even_price']:+g} "
                             f"to break even (reference payout {c['price']:+g}), edge {c['edge'] * 100:+.1f}%, {c['tier']}")
        L.append("")
    return "\n".join(L) + "\n"


def cmd_run() -> None:
    import espn_sync as es
    games, params, today = _fetch_ledger()
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    lines_rows = read_csv(os.path.join(OUT, "lines_log.csv"))
    picks_rows = {r["pick_id"]: r for r in read_csv(os.path.join(OUT, "picks_log.csv"))}
    cache: dict = {}

    def lookup(f):
        if f["_id"] not in cache:
            cache[f["_id"]] = fetch_odds(f)
            import time
            time.sleep(0.15)
        return cache[f["_id"]]
    freeze_started(games, picks_rows, lines_rows)
    doc = run(games, params, today, lookup, lines_rows, picks_rows, os.environ.get("FACTOR_MODE", "").lower() == "live", now)
    lines_rows = log_lines(lines_rows, doc.pop("new_lines"))
    graded = grade_picks(games, picks_rows, lines_rows, now)
    write_csv(os.path.join(OUT, "lines_log.csv"), LINE_COLS, lines_rows)
    write_csv(os.path.join(OUT, "picks_log.csv"), PICK_COLS, sorted(picks_rows.values(), key=lambda r: (r.get("date", ""), r["pick_id"])))
    import prediction_log as plog  # append-only provenance log; never rewritten
    ppath = os.path.join(OUT, "predictions_log.csv")
    lp = {lg: load_params(lg, params.get(lg)) for lg in {r.get("league", "") for r in picks_rows.values()} if lg}
    appended = plog.append(ppath, plog.build_rows(picks_rows, now, {f["_id"]: f for f in games}, lp, params, plog.read_last(ppath)))
    print(f"Prediction log: {appended} new rows appended")
    with open(os.path.join(OUT, "picks_latest.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, default=str)
    with open(os.path.join(OUT, "picks_latest.md"), "w", encoding="utf-8") as fh:
        fh.write(render_md(doc))
    print(f"Markets: {len(doc['games'])} games priced, {len(picks_rows)} picks tracked, {graded} newly graded, {len(lines_rows)} line rows")
    for w in es.WARNINGS[:5]:
        print("WARNING:", w)


def cmd_grade() -> None:
    games, _, _ = _fetch_ledger()
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    lines_rows = read_csv(os.path.join(OUT, "lines_log.csv"))
    picks_rows = {r["pick_id"]: r for r in read_csv(os.path.join(OUT, "picks_log.csv"))}
    freeze_started(games, picks_rows, lines_rows)
    n = grade_picks(games, picks_rows, lines_rows, now)
    write_csv(os.path.join(OUT, "picks_log.csv"), PICK_COLS, sorted(picks_rows.values(), key=lambda r: (r.get("date", ""), r["pick_id"])))
    print(f"Markets graded: {n} picks")


if __name__ == "__main__":
    {"run": cmd_run, "grade": cmd_grade}.get(sys.argv[1] if len(sys.argv) > 1 else "run", cmd_run)()
