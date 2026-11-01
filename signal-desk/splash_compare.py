#!/usr/bin/env python3
"""Compare the user's Splash picks with the model's suggestions.

Input (env SPLASH_PICKS): one pick per line, e.g. `Alabama -7.5`, `Ohio State +3`, `Kansas State PK`.
Read-only against Airtable (never writes Splash fields or results). Writes into the repo:
  intelligence/splash_picks/YYYY-MM-DD-HHMM.md   comparison for this batch
  intelligence/splash_picks_log.csv              cumulative log; intelligence_report.py grades it as games finish
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import close_grade as cg  # noqa: E402
import espn_sync as es  # noqa: E402
import intelligence_report as ir  # noqa: E402

OUT = os.path.join(HERE, "intelligence")
LOG_COLS = ["logged_at", "record_id", "game", "date", "league", "user_team", "user_side", "user_line", "splash_line_in_ledger",
            "model_pick", "model_tier", "model_units", "adjusted_model_side", "matched"]
LINE = re.compile(r"^\s*(?:[-*\u2022]|\d+[.)])?\s*(?P<team>[A-Za-z][A-Za-z0-9 .&'()\-]*?)\s+(?P<line>[+-]\d+(?:\.\d+)?|PK|pk|pick)\s*(?:\(.*\))?\s*$")


def parse_lines(text: str) -> tuple[list[dict], list[str]]:
    picks, bad = [], []
    for raw in (text or "").replace(";", "\n").splitlines():
        if not raw.strip():
            continue
        m = LINE.match(raw)
        if not m:
            bad.append(raw.strip())
            continue
        ln = m.group("line")
        picks.append({"team": m.group("team").strip(), "line": 0.0 if ln.lower() in ("pk", "pick") else float(ln)})
    return picks, bad


def match_game(team: str, games: list[dict]) -> tuple[dict, bool] | None:
    for f in sorted(games, key=lambda g: g.get("Date", "")):
        ish = cg.side_is_home(team, f.get("Home Team", ""), f.get("Away Team", ""))
        if ish is not None:
            return f, ish
    return None


def compare(picks: list[dict], games: list[dict], now: str) -> tuple[list[dict], list[str]]:
    rows, unmatched, used = [], [], set()
    for p in picks:
        hit = match_game(p["team"], games)
        if not hit:
            unmatched.append(f"{p['team']} {p['line']:+g}")
            continue
        f, ish = hit
        used.add(f["_id"])
        mp = cg.parse_pick(f.get("Recommended Side") or "")
        model_home = cg.side_is_home(mp[1], f.get("Home Team", ""), f.get("Away Team", "")) if mp and mp[0] == "spread" else None
        v = f.get("Vegas Implied Home Margin")
        ledger_line = None if v is None else round(-float(v) if ish else float(v), 1)
        adj = f.get("Adj Edge")
        rows.append({"logged_at": now, "record_id": f["_id"], "game": f.get("Game"), "date": (f.get("Date") or "")[:10], "league": f.get("League"),
                     "user_team": p["team"], "user_side": "home" if ish else "away", "user_line": p["line"], "splash_line_in_ledger": ledger_line,
                     "model_pick": f.get("Recommended Side"), "model_tier": f.get("Sharp-Sheet Tier"), "model_units": f.get("Sharp-Sheet Suggested Units"),
                     "adjusted_model_side": None if adj is None else ("home" if float(adj) > 0 else "away"),
                     "matched": "no model pick" if model_home is None else ("yes" if model_home == ish else "no")})
    return rows, unmatched


def render(rows: list[dict], unmatched: list[str], bad: list[str], passes: list[dict], now: str) -> str:
    agree = sum(1 for r in rows if r["matched"] == "yes")
    against = sum(1 for r in rows if r["matched"] == "no")
    L = [f"# Your Splash picks vs the model, {now}", "", f"{len(rows)} picks compared: {agree} matched the model, {against} went against it, "
         f"{len(rows) - agree - against} had no model pick. All model picks are paper picks.", ""]
    L.append(ir.md_table(["Game", "Your pick", "Model pick", "Model tier", "Result"],
                         [[r["game"], f"{r['user_team']} {r['user_line']:+g}", r["model_pick"], r["model_tier"],
                           {"yes": "matched", "no": "WENT AGAINST", "no model pick": "no model pick"}[r["matched"]]] for r in rows]))
    diffs = [r for r in rows if r["splash_line_in_ledger"] is not None and abs(float(r["splash_line_in_ledger"]) - float(r["user_line"])) >= 0.5]
    if diffs:
        L += ["", "Line differs from the Splash line stored in the ledger:"] + [
            f"- {r['game']}: you {float(r['user_line']):+g}, ledger {float(r['splash_line_in_ledger']):+g}" for r in diffs]
    if passes:
        L += ["", "Model suggested (Lean or better), you did not pick:"] + [
            f"- {f.get('Game')}: {f.get('Sharp-Sheet Tier')} {f.get('Recommended Side')}" for f in passes]
    if unmatched:
        L += ["", "Could not match to an upcoming game: " + "; ".join(unmatched)]
    if bad:
        L += ["", "Could not read these lines (use `Team -3.5`): " + "; ".join(bad)]
    return "\n".join(L) + "\n"


def main() -> None:
    token, base = os.environ.get("AIRTABLE_TOKEN", "").strip(), os.environ.get("AIRTABLE_BASE_ID", "").strip()
    if not (token and base):
        raise SystemExit("ERROR: AIRTABLE_TOKEN and AIRTABLE_BASE_ID must be set.")
    es.AIRTABLE_BASE = base
    picks, bad = parse_lines(os.environ.get("SPLASH_PICKS", ""))
    if not picks:
        raise SystemExit("No readable picks in SPLASH_PICKS.")
    today = ir.central_today().isoformat()
    games = [r["fields"] | {"_id": r["id"]} for r in ir.fetch(base, token, ir.LEDGER, "{Record Type}='Game'")]
    upcoming = [f for f in games if (f.get("Date") or "")[:10] >= today and f.get("Home Score") is None]
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%MZ")
    rows, unmatched = compare(picks, upcoming, now)
    picked_ids = {r["record_id"] for r in rows}
    passes = [f for f in upcoming if f.get("Sharp-Sheet Tier") in ("Lean", "Strong Play", "Max Play") and f["_id"] not in picked_ids]
    text = render(rows, unmatched, bad, passes, now)
    os.makedirs(os.path.join(OUT, "splash_picks"), exist_ok=True)
    with open(os.path.join(OUT, "splash_picks", dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d-%H%M") + ".md"), "w", encoding="utf-8") as fh:
        fh.write(text)
    path = os.path.join(OUT, "splash_picks_log.csv")
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=LOG_COLS)
        if new:
            w.writeheader()
        w.writerows(rows)
    print(text)


if __name__ == "__main__":
    main()
