#!/usr/bin/env python3
"""Publish a truthful submission status without publishing partial failed outputs."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import splash_import as si


def publish_readiness(now):
    """Run the existing readiness validator; never turn intake success into ready."""
    import validate_artifacts as va
    try:
        report = va.validate(si.HERE, now)
    except Exception as exc:
        report = {"checked_at": now.isoformat(), "ready": False,
                  "errors": [f"Readiness execution failed: {type(exc).__name__}"]}
    try:
        report["source_revision"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=si.HERE, stderr=subprocess.DEVNULL).decode().strip()
    except (OSError, subprocess.CalledProcessError):
        report["source_revision"] = None
    day = now.astimezone(va.CENTRAL).date().isoformat()
    names = [
        "validate_artifacts.py", "intelligence/latest.json", "intelligence/latest.md",
        f"intelligence/data/{day}.json", "data/snapshot.json", "data/ops_status.json",
        "data/producer_health/markets.json", "intelligence/splash_lines/latest.md",
        "intelligence/splash_pricecheck/latest.json", "intelligence/splash_pricecheck/latest.md",
    ]
    report["input_git_blobs"] = {}
    for name in names:
        path = si.HERE / name
        raw = path.read_bytes() if path.is_file() else None
        report["input_git_blobs"][name] = (
            hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest() if raw is not None else None)
    report["note"] = "Repository-executed readiness; import acceptance is a separate decision."
    si.save_json(si.HERE / "intelligence/splash_import/readiness_latest.json", report)
    return report


def admitted_paths(names):
    """One source, one review, or the source and its review in one owner push."""
    base = pathlib.PurePosixPath("signal-desk/intelligence/splash_import")
    paths = [pathlib.PurePosixPath(n) for n in names]
    si.need(1 <= len(paths) <= 2 and len(set(paths)) == len(paths),
            "submit exactly one source, optionally with its exact owner review")
    for p in paths:
        si.need(p.parent in (base / "inbox", base / "reviews")
                and re.fullmatch(r"SPL-[LPC]-\d{8}-\d{4}\.json", p.name),
                "unsupported submission path or date_code")
    si.need(len({p.name for p in paths}) == 1, "a push must address exactly one source date_code")
    return next((p for p in paths if p.parent.name == "inbox"), paths[0])


def process(path, now=None):
    path = pathlib.Path(path).resolve()
    base = si.HERE / "intelligence/splash_import"
    si.need(path.parent in (base / "inbox", base / "reviews")
            and re.fullmatch(r"SPL-[LPC]-\d{8}-\d{4}\.json", path.name),
            "unsupported submission path or date_code")
    now = now or dt.datetime.now(dt.timezone.utc)
    source = base / "inbox" / path.name
    status = {
        "schema": "signal-desk.splash-submission-status.v1",
        "date_code": path.stem,
        "processed_at_utc": now.isoformat(),
        "airtable_writes": 0,
    }
    intelligence = si.HERE / "intelligence"
    # execute() stages its calculations before saving, but a late exception can
    # still interrupt output writes. Restore the entire pre-run intelligence
    # tree before publishing a failure; never commit half an accepted import.
    with tempfile.TemporaryDirectory(prefix="splash-transaction-") as tmp:
        backup = pathlib.Path(tmp) / "intelligence"
        shutil.copytree(intelligence, backup)
        try:
            si.need(source.is_file(), "original pending inbox source is missing; do not recreate accepted inputs")
            status["input_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
            si.execute(source, now=now)
            receipt_path = base / "receipts" / path.name
            receipt = json.loads(receipt_path.read_bytes())
            si.need(receipt.get("status") == "accepted", "accepted receipt is missing")
            si.need(receipt.get("input_sha256") == status["input_sha256"], "receipt checksum mismatch")
            si.need(receipt["expected_rows"] == receipt["actual_new_rows"], "receipt row-count mismatch")
            archive = si.HERE / "intelligence" / (
                "splash_lines" if receipt["kind"] == "lines" else "splash_picks") / "raw" / path.name
            processed = base / "processed" / path.name
            for preserved in (archive, processed):
                si.need(preserved.is_file()
                        and hashlib.sha256(preserved.read_bytes()).hexdigest() == status["input_sha256"],
                        "original archive or processed-source checksum mismatch")
            readiness = publish_readiness(now)
            status.update({
                "status": "accepted",
                "receipt_path": f"signal-desk/intelligence/splash_import/receipts/{path.name}",
                "receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
                "expected_rows": receipt["expected_rows"],
                "actual_new_rows": receipt["actual_new_rows"],
                "duplicate_tickets": len(receipt["duplicates"]),
                "artifacts_ready": readiness.get("ready") is True,
                "requested_window_coverage_checked": False,
            })
            result = 0
        except Exception as exc:
            shutil.rmtree(intelligence)
            shutil.copytree(backup, intelligence)
            expected = isinstance(exc, (si.Rejected, ValueError, TypeError, KeyError))
            status.update({
                "status": "rejected" if expected else "failed",
                "first_error": str(exc) if expected else f"Processing failed: {type(exc).__name__}",
                "accepted_rows": 0,
                "note": "This is not an accepted import. Original pending source and owner review are retained.",
            })
            result = 1
    si.save_json(base / "status" / path.name, status)
    print(json.dumps(status, indent=2))
    return result


if __name__ == "__main__":
    si.need(len(sys.argv) == 2, "supply one source or review filename")
    raise SystemExit(process(pathlib.Path(sys.argv[1])))
