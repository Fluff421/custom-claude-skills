#!/usr/bin/env python3
"""Signal Desk snapshot: regenerates LEDGER.md and data/snapshot.json from Airtable.

Airtable is the source of truth. Reads graded Game rows from the Signal Desk Ledger and
writes a plain-text record (ATS / ML / totals, by tier) so the repo files never disagree
with the live system. Read-only against Airtable. Never edits MODEL.md.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import espn_sync as es

LEDGER = "tbl3tFHFhvyNMpksE"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_MD = os.path.join(HERE, "LEDGER.md")
OUT_JSON = os.path.join(HERE, "data", "snapshot.json")
RESULT_KEY = {"Win": "hits", "Loss": "misses", "Push": "pushes"}
TIER_ORDER = ("Max Play", "Strong Play", "Lean", "No Play")
MIN_SAMPLE = 30


def blank() -> dict:
    return {"hits": 0, "misses": 0, "pushes": 0}


def fetch_graded(base: str, token: str) -> list[dict]:
    formula = "AND({Record Type}='Game',OR({Grade}='Win',{Grade}='Loss',{Grade}='Push'))"
    out, offset = [], None
    while True:
        url = f"https://api.airtable.com/v0/{base}/{LEDGER}?pageSize=100&filterByFormula=" + urllib.parse.quote(formula)
        if offset:
            url += "&offset=" + urllib.parse.quote(offset, safe="")
        page = json.loads(es.http_get(url, es.at_headers(token)))
        out.extend(page.get("records", []))
        offset = page.get("offset")
        if not offset:
            return out


def market_of(fields: dict) -> str:
    side = (fields.get("Recommended Side") or "").lower()
    if "(total)" in side:
        return "totals"
    if "(moneyline)" in side or "(ml)" in side:
        return "ml"
    return "ats"


def summarize(rows: list[dict]) -> dict:
    ledger = {"ats": blank(), "ml": blank(), "totals": blank()}
    tiers: dict[str, dict] = {}
    for r in rows:
        f = r["fields"]
        key = RESULT_KEY.get(f.get("Grade", ""))
        if not key:
            continue
        ledger[market_of(f)][key] += 1
        tier = f.get("Sharp-Sheet Tier") or "Untiered"
        t = tiers.setdefault(tier, {**blank(), "clv": []})
        t[key] += 1
        if f.get("Sharp-Sheet CLV Points") is not None:
            t["clv"].append(float(f["Sharp-Sheet CLV Points"]))
    return {"ledger": ledger, "tiers": tiers}


def record(c: dict) -> str:
    return f"{c['hits']}-{c['misses']}-{c['pushes']}"


def size(c: dict) -> int:
    return c["hits"] + c["misses"] + c["pushes"]


def hit_rate(c: dict) -> str:
    decided = c["hits"] + c["misses"]
    return f"{c['hits'] / decided:.1%}" if decided else "n/a"


def render_md(today: str, summary: dict, total: int) -> str:
    led = summary["ledger"]
    if total == 0:
        head = "No graded 2026 picks. Regular-season ATS ledger starts after first graded week."
    else:
        head = f"{total} graded picks as of {today}."
    lines = ["# Signal Desk Ledger", "",
             f"Auto-generated from the Airtable Signal Desk Ledger by signal-desk/snapshot.py ({today}). Do not edit by hand.",
             "", head, "",
             f"ATS: {record(led['ats'])} (n={size(led['ats'])})",
             f"ML: {record(led['ml'])} (n={size(led['ml'])})",
             f"Totals: {record(led['totals'])} (n={size(led['totals'])})", ""]
    small = [k for k, v in led.items() if size(v) < MIN_SAMPLE]
    if len(small) == 3:
        lines.append(f"Flag: n < {MIN_SAMPLE} for all.")
    elif small:
        lines.append(f"Flag: n < {MIN_SAMPLE} for {', '.join(small)}.")
    if summary["tiers"]:
        lines += ["", "## By sharp-sheet tier", "", "| Tier | Record | Hit rate | Avg CLV (pts) | n |", "|---|---|---|---|---|"]
        order = [t for t in TIER_ORDER if t in summary["tiers"]] + sorted(t for t in summary["tiers"] if t not in TIER_ORDER)
        for name in order:
            t = summary["tiers"][name]
            clv = f"{sum(t['clv']) / len(t['clv']):+.2f}" if t["clv"] else "n/a"
            lines.append(f"| {name} | {record(t)} | {hit_rate(t)} | {clv} | {size(t)} |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    token = os.environ.get("AIRTABLE_TOKEN", "").strip()
    base = os.environ.get("AIRTABLE_BASE_ID", "").strip()
    if not (token and base):
        raise SystemExit("ERROR: AIRTABLE_TOKEN and AIRTABLE_BASE_ID must be set.")
    try:
        rows = fetch_graded(base, token)
    except RuntimeError as exc:
        raise SystemExit(f"ERROR reading ledger {LEDGER} in {base}: {exc}")
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    summary = summarize(rows)
    total = sum(size(c) for c in summary["ledger"].values())
    weeks = {"nfl_week": None, "ncaaf_week": None}
    try:
        with open(OUT_JSON, encoding="utf-8") as fh:
            old = json.load(fh)
        weeks = {k: old.get(k) for k in weeks}
    except (OSError, ValueError):
        pass
    snap = {"date": today, **weeks, "ledger": summary["ledger"],
            "tiers": {k: {**{x: v[x] for x in ("hits", "misses", "pushes")},
                          "avg_clv": round(sum(v["clv"]) / len(v["clv"]), 2) if v["clv"] else None}
                      for k, v in summary["tiers"].items()},
            "graded_picks": total,
            "notes": "Generated from Airtable by signal-desk/snapshot.py. Ensemble weight 0."}
    md = render_md(today, summary, total)
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write(md)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(snap, indent=1) + "\n")
    print(md)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("## Snapshot\n\n" + md + "\n")


if __name__ == "__main__":
    main()
