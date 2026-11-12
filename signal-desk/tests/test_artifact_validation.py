"""Briefing readiness is evaluated from source timestamps, never checkout mtimes."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "validate_artifacts.py"


class Readiness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.write("intelligence/latest.json", {"date": "2026-11-06", "generated_at": "2026-11-06T13:45:00Z"})
        self.write("intelligence/data/2026-11-06.json", {"date": "2026-11-06", "generated_at": "2026-11-06T13:45:00Z"})
        self.write("intelligence/latest.md", "# Signal Desk 2026-11-06\n\nPaper picks.")
        self.write("data/snapshot.json", {"generated_at": "2026-11-06T13:40:00Z"})
        self.write("intelligence/splash_lines/latest.md", "# Splash line snapshot (2026-11-06 07:16:00 CST)\n\nOne game.")
        self.write("intelligence/splash_pricecheck/latest.md", "# Price check\n\nOne game.")
        self.write("intelligence/splash_pricecheck/latest.json", {
            "generated_at": "2026-11-06T13:40:00Z", "snapshot_age_hours": 0.4, "games": [{"game": "A @ B"}]})
        self.write("data/ops_status.json", {
            "generated_at_utc": "2026-11-06T13:40:00Z", "workflow_health": [{
                "file": "close-grade.yml", "runs": [{"created_at": "2026-11-06T13:37:00Z",
                "event": "schedule", "conclusion": "success", "health": "ok", "summary": {"mode": "LIVE"}}]}] + [
                    {"file": name, "runs": [{"created_at": "2026-11-06T13:30:00Z",
                     "event": "schedule", "conclusion": "success", "health": "ok", "summary": {"mode": "LIVE"}}]}
                    for name in ("espn-sync.yml", "picks.yml", "context-calibrate.yml", "injury-pull.yml")]})

    def test_missing_required_producer_evidence_fails_closed(self):
        ops = json.loads((self.root / "data/ops_status.json").read_text())
        ops["workflow_health"] = [w for w in ops["workflow_health"] if w["file"] != "espn-sync.yml"]
        self.write("data/ops_status.json", ops)
        result, report = self.run_gate()
        self.assertEqual(result.returncode, 1)
        self.assertTrue(any("espn-sync.yml" in e for e in report["errors"]))

    def test_stale_healthy_producer_does_not_pass(self):
        ops = json.loads((self.root / "data/ops_status.json").read_text())
        next(w for w in ops["workflow_health"] if w["file"] == "espn-sync.yml")["runs"][0]["created_at"] = "2026-11-06T10:00:00Z"
        self.write("data/ops_status.json", ops)
        result, report = self.run_gate()
        self.assertEqual(result.returncode, 1)
        self.assertTrue(any("espn-sync.yml: age" in e for e in report["errors"]))

    def test_successful_dry_run_is_not_production_evidence(self):
        ops = json.loads((self.root / "data/ops_status.json").read_text())
        next(w for w in ops["workflow_health"] if w["file"] == "picks.yml")["runs"][0]["summary"]["mode"] = "DRY RUN"
        self.write("data/ops_status.json", ops)
        result, report = self.run_gate()
        self.assertEqual(result.returncode, 1)
        self.assertTrue(any("picks.yml: latest producer" in e for e in report["errors"]))

    def test_missing_snapshot_generation_evidence_fails_closed(self):
        self.write("data/snapshot.json", {"date": "2026-11-06"})
        result, report = self.run_gate()
        self.assertEqual(result.returncode, 1)
        self.assertTrue(any("snapshot:" in e for e in report["errors"]))

    def write(self, name, value):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")

    def run_gate(self, now="2026-11-06T14:30:00Z"):
        result = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), "--now", now],
                                capture_output=True, text=True)
        return result, json.loads(result.stdout)

    def test_fresh_artifacts_pass_and_missing_pricecheck_fails(self):
        result, report = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(report["ready"])
        (self.root / "intelligence/splash_pricecheck/latest.md").unlink()
        result, report = self.run_gate()
        self.assertEqual(result.returncode, 1)
        self.assertFalse(report["ready"])
        self.assertTrue(any("pricecheck" in e for e in report["errors"]))

    def test_old_source_cannot_be_freshened_by_regeneration_or_checkout(self):
        result, report = self.run_gate("2026-11-06T18:30:00Z")
        self.assertEqual(result.returncode, 1)
        self.assertTrue(any("narrative:" in e for e in report["errors"]))
        self.write("intelligence/splash_pricecheck/latest.json", {
            "generated_at": "2026-11-06T14:00:00Z", "snapshot_age_hours": 170, "games": []})
        result, report = self.run_gate()
        self.assertEqual(result.returncode, 1)
        self.assertTrue(any("underlying_quotes" in e for e in report["errors"]))

    def test_success_with_degraded_coverage_does_not_pass(self):
        ops = json.loads((self.root / "data/ops_status.json").read_text())
        ops["workflow_health"][0]["runs"][0]["health"] = "degraded"
        self.write("data/ops_status.json", ops)
        result, report = self.run_gate()
        self.assertEqual(result.returncode, 1)
        self.assertTrue(any("not healthy" in e for e in report["errors"]))

    def test_previous_central_day_future_time_and_bad_metadata_fail_closed(self):
        self.write("intelligence/latest.json", {"date": "2026-11-05", "generated_at": "2026-11-07T14:00Z"})
        result, report = self.run_gate()
        self.assertEqual(result.returncode, 1)
        self.assertFalse(report["ready"])
        self.write("data/ops_status.json", [])
        result, report = self.run_gate()
        self.assertEqual(result.returncode, 1)
        self.assertFalse(report["ready"])

    def test_json_and_markdown_must_match_when_digest_is_present(self):
        for name in ("intelligence/latest.json", "intelligence/data/2026-11-06.json"):
            self.write(name, {"date": "2026-11-06", "generated_at": "2026-11-06T13:45:00Z",
                              "narrative_sha256": "0" * 64})
        result, report = self.run_gate()
        self.assertEqual(result.returncode, 1)
        self.assertTrue(any("content does not match" in e for e in report["errors"]))

    def test_weekly_board_passes_with_warning_but_older_than_a_week_fails(self):
        self.write("intelligence/splash_lines/latest.md", "# Splash line snapshot (2026-11-01 20:19:00 CST)\n\nOne game.")
        self.write("intelligence/splash_pricecheck/latest.json", {
            "generated_at": "2026-11-06T13:40:00Z", "snapshot_age_hours": 113, "games": []})
        result, report = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(report["policy"]["board_hours"], 168)
        self.assertTrue(any("splash_board" in w for w in report["warnings"]))
        self.write("intelligence/splash_lines/latest.md", "# Splash line snapshot (2026-10-30 08:00:00 CDT)\n\nOne game.")
        result, report = self.run_gate()
        self.assertEqual(result.returncode, 1)
        self.assertTrue(any(e.startswith("splash_board: age") for e in report["errors"]))

    def test_board_within_the_weekly_limit_still_warns_after_four_hours(self):
        self.write("intelligence/splash_lines/latest.md", "# Splash line snapshot (2026-11-06 00:00:00 CST)\n\nOne game.")
        self.write("intelligence/splash_pricecheck/latest.json", {
            "generated_at": "2026-11-06T13:40:00Z", "snapshot_age_hours": 8, "games": []})
        result, report = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(report["ready"])
        self.assertEqual(len(report["warnings"]), 2)
