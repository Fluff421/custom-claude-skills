#!/usr/bin/env python3
"""Append-only prediction log (Phase 2, priority 1).

`picks_log.csv` is upserted in place, so a pick's earlier numbers are overwritten. This file keeps every
distinct prediction ever issued, with enough provenance to reproduce it, and is never rewritten:
rows are only appended, and a new row is written only when a pick's numbers or configuration change.

Columns follow the post-audit spec: model_version, config_hash, data_cutoff_timestamp, league,
sigma_version, k_version, prediction_timestamp, event_id, plus an explicit event_definition so one
probability column never mixes spread-cover, total and outright-win events.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os

PRED_COLS = ["prediction_id", "prediction_timestamp", "data_cutoff_timestamp", "odds_fetched_at", "event_id", "game_ids",
             "pick_id", "league", "market", "event_definition", "selection", "side", "line", "price", "prob", "edge",
             "edge_unit", "tier", "units", "model_version", "config_hash", "sigma_version", "k_version"]

EVENT_DEFINITION = {
    "spread": "spread_cover", "alt_spread": "spread_cover", "total": "total_over_under",
    "moneyline": "outright_win", "teaser_leg": "teased_spread_or_total_cover", "parlay_leg": "parlay_leg_cover",
    "parlay": "parlay_all_legs_win", "teaser": "teaser_all_legs_win",
}
# fields whose change means a new prediction (timestamps excluded on purpose)
_FINGERPRINT = ("line", "price", "prob", "edge", "tier", "units", "config_hash")


def model_version() -> str:
    sha = os.environ.get("GITHUB_SHA", "").strip()
    return sha[:12] if sha else "local"


def config_hash(params: dict) -> str:
    return hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()[:12]


def sigma_version(params: dict, airtable_fields: dict | None) -> str:
    at = (airtable_fields or {}).get("Sigma")
    return (f"markets.sigma_margin={params.get('sigma_margin')};markets.sigma_total={params.get('sigma_total')};"
            f"airtable.Sigma={at if at is not None else 'unset'}")


def k_version(params: dict, airtable_fields: dict | None) -> str:
    src = "airtable" if (airtable_fields or {}).get("Market Blend K") is not None else "prior"
    return f"k_margin={params.get('k_margin')}({src},margin-blend);k_total={params.get('k_total')}"


def read_last(path: str) -> dict[str, dict]:
    """Latest logged row per pick_id."""
    last: dict[str, dict] = {}
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                last[r["pick_id"]] = r
    return last


def _fp(row: dict) -> tuple:
    return tuple(str(row.get(k, "")) for k in _FINGERPRINT)


def build_rows(picks_rows: dict, now: str, games_by_id: dict, league_params: dict, airtable_params: dict,
               last: dict[str, dict]) -> list[dict]:
    """New prediction rows for picks refreshed this run (last_updated == now, not frozen) whose numbers changed."""
    out = []
    for pid, r in sorted(picks_rows.items()):
        if r.get("last_updated") != now or str(r.get("frozen")) == "1":
            continue
        league = r.get("league", "")
        p = league_params.get(league, {})
        gids = [g for g in (r.get("game_ids") or "").split("+") if g]
        games = [games_by_id.get(g, {}) for g in gids]
        pulled = sorted(str(g.get("ESPN Pulled At")) for g in games if g.get("ESPN Pulled At"))
        row = {
            "prediction_timestamp": now, "data_cutoff_timestamp": pulled[-1] if pulled else "", "odds_fetched_at": now,
            "event_id": "+".join(str(g.get("ESPN Event ID") or "") for g in games), "game_ids": r.get("game_ids", ""),
            "pick_id": pid, "league": league, "market": r.get("market", ""),
            "event_definition": EVENT_DEFINITION.get(r.get("market", ""), "other"),
            **{k: r.get(k, "") for k in ("selection", "side", "line", "price", "prob", "edge", "edge_unit", "tier", "units")},
            "model_version": model_version(), "config_hash": config_hash(p),
            "sigma_version": sigma_version(p, airtable_params.get(league)),
            "k_version": k_version(p, airtable_params.get(league)),
        }
        prev = last.get(pid)
        if prev and _fp(prev) == _fp(row):
            continue
        row["prediction_id"] = hashlib.sha256(f"{pid}|{now}|{_fp(row)}".encode()).hexdigest()[:16]
        out.append(row)
    return out


def append(path: str, rows: list[dict]) -> int:
    """Append only. Never rewrites or reorders existing rows."""
    if not rows:
        return 0
    new = not os.path.exists(path) or os.path.getsize(path) == 0
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=PRED_COLS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerows(rows)
    return len(rows)
