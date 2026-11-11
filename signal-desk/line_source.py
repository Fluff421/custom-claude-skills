"""Line-source report cards: score ESPN-priced and Splash-priced picks separately.

A graded pick is priced off one of two lines:
  - "espn":   picks.py found no Splash line and priced it off the ESPN line. It labels the pick in
              Sharp-Sheet Data Completeness with "priced off ESPN line (no Splash line)".
  - "splash": the pick was priced against the Splash line in Vegas Implied Home Margin.
Anything else is "unknown" and is reported but never scored into either card.

Report cards are read-only: they never change a pick, unit, tier, sigma or k. calibrate.py prints them every
day and stores them in learning_params.json under "report_cards".

LEARN_LINE_SOURCE chooses which picks feed the live learning that sets tiers and units
(Brier/log loss written to Model Parameters, tier multipliers, CLV unit gate, unit-cap counts):
  all    (default) every graded pick, today's behaviour, nothing changes
  splash only Splash-priced picks, so units are earned on the line the owner actually locks
A human sets the repo variable; nothing switches itself.
"""
from __future__ import annotations

import math
import os

ESPN_MARK = "priced off ESPN line"
SOURCES = ("splash", "espn")
TIERS = ("Max Play", "Strong Play", "Lean", "No Play")
BUCKETS = [(0.5, 0.55), (0.55, 0.60), (0.60, 0.65), (0.65, 0.70), (0.70, 0.80), (0.80, 1.01)]
MODES = ("all", "splash")


def source(f: dict) -> str:
    note = str(f.get("Sharp-Sheet Data Completeness") or "")
    if ESPN_MARK in note:
        return "espn"
    if f.get("Vegas Implied Home Margin") is not None:
        return "splash"
    return "unknown"


def learn_mode() -> str:
    m = os.environ.get("LEARN_LINE_SOURCE", "all").strip().lower() or "all"
    if m not in MODES:
        raise SystemExit(f"ERROR: LEARN_LINE_SOURCE must be one of {MODES}, got {m!r}")
    return m


def for_learning(fs: list[dict], mode: str | None = None) -> list[dict]:
    """Rows that feed live learning under the chosen mode."""
    mode = mode or learn_mode()
    return list(fs) if mode == "all" else [f for f in fs if source(f) == "splash"]


def airtable_filter(mode: str | None = None) -> str:
    """Extra Airtable formula clause for picks.graded_counts (empty under 'all')."""
    mode = mode or learn_mode()
    if mode == "all":
        return ""
    return (",{Vegas Implied Home Margin}!=''"
            f",FIND('{ESPN_MARK}',{{Sharp-Sheet Data Completeness}}&'')=0")


def _f(x):
    try:
        return None if x is None or x == "" else float(x)
    except (TypeError, ValueError):
        return None


def _mean_se(v: list[float]):
    n = len(v)
    if not n:
        return None, None
    m = sum(v) / n
    se = math.sqrt(sum((x - m) ** 2 for x in v) / (n - 1)) / math.sqrt(n) if n > 1 else None
    return round(m, 3), None if se is None else round(se, 3)


def card(fs: list[dict]) -> dict:
    """One report card from graded rows of one league and one line source."""
    graded = [f for f in fs if f.get("Grade") in ("Win", "Loss", "Push")]
    w = sum(1 for f in graded if f["Grade"] == "Win")
    l = sum(1 for f in graded if f["Grade"] == "Loss")
    out = {"n": len(graded), "wins": w, "losses": l, "pushes": len(graded) - w - l,
           "hit_rate": round(w / (w + l), 3) if w + l else None}
    ps, ys = [], []
    for f in graded:
        p = _f(f.get("Sharp-Sheet Est. Win Prob %"))
        if f["Grade"] == "Push" or p is None:
            continue
        ps.append(p)
        ys.append(1.0 if f["Grade"] == "Win" else 0.0)
    out["n_prob"] = len(ps)
    if len(ps) >= 5:
        eps = 0.02
        out["brier"] = round(sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ps), 4)
        out["log_loss"] = round(sum(-(y * math.log(max(p, eps)) + (1 - y) * math.log(max(1 - p, eps)))
                                    for p, y in zip(ps, ys)) / len(ps), 4)
        table = []
        for lo, hi in BUCKETS:
            b = [(p, y) for p, y in zip(ps, ys) if lo <= p < hi]
            if b:
                table.append({"bucket": f"{lo:.0%}-{hi:.0%}", "n": len(b),
                              "pred": round(sum(p for p, _ in b) / len(b), 3),
                              "actual": round(sum(y for _, y in b) / len(b), 3)})
        out["calibration"] = table
    clv = [x for x in (_f(f.get("Sharp-Sheet CLV Points")) for f in graded) if x is not None]
    out["clv_n"] = len(clv)
    out["clv_mean"], out["clv_se"] = _mean_se(clv)
    tiers = {}
    for t in TIERS:
        tf = [f for f in graded if f.get("Sharp-Sheet Tier") == t]
        if not tf:
            continue
        tw = sum(1 for f in tf if f["Grade"] == "Win")
        tl = sum(1 for f in tf if f["Grade"] == "Loss")
        tc = [x for x in (_f(f.get("Sharp-Sheet CLV Points")) for f in tf) if x is not None]
        m, se = _mean_se(tc)
        tiers[t] = {"n": len(tf), "wins": tw, "losses": tl, "clv_n": len(tc), "clv_mean": m, "clv_se": se}
    out["tiers"] = tiers
    return out


def report_cards(fs: list[dict]) -> dict:
    """{'splash': card, 'espn': card, 'unknown': n} for one league's graded rows."""
    split = {s: [] for s in SOURCES}
    unknown = 0
    for f in fs:
        s = source(f)
        if s in split:
            split[s].append(f)
        else:
            unknown += 1
    return {**{s: card(v) for s, v in split.items()}, "unknown": unknown}


def summary_lines(league: str, cards: dict, mode: str) -> list[str]:
    lines = [f"{league} report cards (live learning uses: {mode}; unclassified rows: {cards['unknown']})"]
    for s in SOURCES:
        c = cards[s]
        if not c["n"]:
            lines.append(f"  {s}-line: no graded picks yet")
            continue
        parts = [f"{c['wins']}-{c['losses']}-{c['pushes']}"]
        if c["hit_rate"] is not None:
            parts.append(f"hit {c['hit_rate']:.1%}")
        if "brier" in c:
            parts.append(f"Brier {c['brier']}, log loss {c['log_loss']}")
        if c["clv_mean"] is not None:
            parts.append(f"CLV {c['clv_mean']:+} (se {c['clv_se']}, n={c['clv_n']})")
        lines.append(f"  {s}-line: n={c['n']}, " + ", ".join(parts))
    return lines
