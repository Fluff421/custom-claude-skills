"""Read-only, fail-closed readiness check. Optional --output writes diagnostics only."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

CENTRAL = ZoneInfo("America/Chicago")


def timestamp(value):
    t = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("timestamp needs a timezone")
    return t


def validate(root, now, narrative_hours=4, grade_hours=2, board_hours=12, pricecheck_hours=4):
    errors, warnings, checks = [], [], {}
    today = now.astimezone(CENTRAL).date().isoformat()

    def read(name, structured=False):
        try:
            text = (root / name).read_text(encoding="utf-8")
            if not text.strip():
                raise ValueError("empty file")
            return json.loads(text) if structured else text
        except (OSError, ValueError) as exc:
            errors.append(f"{name}: {exc}")
            return {} if structured else ""

    def fresh(name, value, limit):
        try:
            age = (now - timestamp(value)).total_seconds() / 3600
            checks[name] = {"age_hours": round(age, 3), "max_age_hours": limit}
            if age < -5 / 60 or age >= limit:
                errors.append(f"{name}: age {age:.2f}h outside [0, {limit})h (5m clock tolerance)")
            elif name in ("splash_board", "pricecheck_underlying_quotes") and age >= 4:
                warnings.append(f"{name}: {age:.2f}h old; exceeds 4h market warning guard. Refresh Splash before relying on prices.")
        except (ValueError, TypeError) as exc:
            errors.append(f"{name}: invalid timestamp ({exc})")

    narrative = read("intelligence/latest.json", True)
    dated = read(f"intelligence/data/{today}.json", True)
    md = read("intelligence/latest.md")
    if narrative.get("date") != today or dated != narrative:
        errors.append("narrative: latest.json must equal today's dated JSON (Central date)")
    if today not in md.split("\n", 1)[0]:
        errors.append("narrative: Markdown heading is not for today (Central date)")
    digest = narrative.get("narrative_sha256")
    if digest and hashlib.sha256(md.encode()).hexdigest() != digest:
        errors.append("narrative: Markdown content does not match JSON provenance")
    fresh("narrative", narrative.get("generated_at"), narrative_hours)
    snapshot = read("data/snapshot.json", True)
    fresh("snapshot", snapshot.get("generated_at"), 26)

    board = read("intelligence/splash_lines/latest.md")
    match = re.search(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) (CST|CDT)", board.split("\n", 1)[0])
    try:
        if not match:
            raise ValueError("missing source capture timestamp")
        captured = dt.datetime.strptime(match[1], "%Y-%m-%d %H:%M:%S").replace(tzinfo=CENTRAL)
        if captured.tzname() != match[2]:
            raise ValueError("Central offset label disagrees with date")
        fresh("splash_board", captured.isoformat(), board_hours)
    except ValueError as exc:
        errors.append(f"splash_board: {exc}")

    read("intelligence/splash_pricecheck/latest.md")
    prices = read("intelligence/splash_pricecheck/latest.json", True)
    fresh("pricecheck", prices.get("generated_at"), pricecheck_hours)
    try:
        # Regeneration does not make the underlying manual quote new.
        quote_time = timestamp(prices.get("generated_at")) - dt.timedelta(hours=float(prices["snapshot_age_hours"]))
        fresh("pricecheck_underlying_quotes", quote_time.isoformat(), board_hours)
        if not isinstance(prices["games"], list):
            raise ValueError("games must be a list")
    except (KeyError, ValueError, TypeError) as exc:
        errors.append(f"pricecheck: invalid source provenance ({exc})")

    ops = read("data/ops_status.json", True)
    fresh("ops_export", ops.get("generated_at_utc"), narrative_hours)
    runs = [r for wf in ops.get("workflow_health", []) if wf.get("file") == "close-grade.yml"
            for r in wf.get("runs", []) if r.get("event") != "pull_request"]
    try:
        latest = max(runs, key=lambda r: timestamp(r.get("created_at")))
        fresh("close_grade", latest["created_at"], grade_hours)
        if (latest.get("conclusion") != "success" or latest.get("health") != "ok"
                or latest.get("summary", {}).get("mode") != "LIVE"):
            errors.append("close_grade: latest run is not healthy, successful and LIVE")
    except (ValueError, KeyError, TypeError) as exc:
        errors.append(f"close_grade: no verifiable run ({exc})")
    # A recent success label alone is not proof of clean coverage.
    workflows = {wf.get("file"): wf for wf in ops.get("workflow_health", [])}
    injury_hours = 4 if now.astimezone(CENTRAL).weekday() in (2, 3, 4, 5) else 26
    for name, max_age in (("injury-pull.yml", injury_hours), ("espn-sync.yml", 4),
                          ("picks.yml", 4), ("context-calibrate.yml", 26)):
        wf = workflows.get(name, {})
        candidates = [r for r in wf.get("runs", []) if r.get("event") != "pull_request"]
        if not candidates:
            errors.append(f"{name}: required producer evidence is missing")
            continue
        latest = max(candidates, key=lambda r: timestamp(r.get("created_at")))
        fresh(name, latest.get("created_at"), max_age)
        if (latest.get("conclusion") != "success" or latest.get("health") != "ok"
                or latest.get("summary", {}).get("mode") != "LIVE"):
            errors.append(f"{name}: latest producer run is not healthy, successful and LIVE")
    health_path = root / "data/producer_health/markets.json"
    if health_path.exists():
        health = read("data/producer_health/markets.json", True)
        if health.get("status") not in ("ok", "no_games"):
            errors.append("markets: partial feed failure recorded by producer")
    return {"checked_at": now.isoformat(), "central_date": today, "ready": not errors,
            "policy": {"narrative_hours": narrative_hours, "grade_hours": grade_hours,
                       "board_hours": board_hours, "pricecheck_hours": pricecheck_hours},
            "checks": checks, "errors": errors, "warnings": warnings, "paper_picks_only": True}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    p.add_argument("--now", help="timezone-aware ISO timestamp, for reproducible checks")
    p.add_argument("--output", type=Path)
    for name, default in (("narrative", 4), ("grade", 2), ("board", 12), ("pricecheck", 4)):
        p.add_argument(f"--{name}-max-age-hours", type=float, default=default)
    args = p.parse_args()
    try:
        now = timestamp(args.now) if args.now else dt.datetime.now(dt.timezone.utc)
        limits = [getattr(args, f"{name}_max_age_hours") for name in ("narrative", "grade", "board", "pricecheck")]
        if any(not 0 < v < float("inf") for v in limits):
            raise ValueError("age limits must be positive and finite")
        report = validate(args.root, now, *limits)
    except (ValueError, TypeError, AttributeError) as exc:
        report = {"ready": False, "errors": [f"invalid metadata/configuration: {exc}"]}
    text = json.dumps(report, indent=2) + "\n"
    print(text, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
