"""Missing or failed injury data is a visible warning, never a stop for picks, grading or learning."""
import json
import unittest

from tests import test_artifact_validation as base


class InjuryNonBlocking(unittest.TestCase):
    # Reuse the shared fixture without re-running the base class's tests.
    setUp, write, run_gate = base.Readiness.setUp, base.Readiness.write, base.Readiness.run_gate

    def injury(self, ops):
        return next(w for w in ops["workflow_health"] if w["file"] == "injury-pull.yml")

    def edit(self, change):
        ops = json.loads((self.root / "data/ops_status.json").read_text())
        change(ops)
        self.write("data/ops_status.json", ops)

    def assert_degraded_but_ready(self, text):
        result, report = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(report["ready"])
        self.assertFalse(any("injury-pull.yml" in e for e in report["errors"]))
        self.assertIn("injury_data", report["degraded"])
        self.assertEqual(report["checks"]["injury-pull.yml"]["status"], "degraded")
        warning = next(w for w in report["warnings"] if w.startswith("injury-pull.yml"))
        self.assertIn(text, warning)
        self.assertIn("picks, grading and learning continue", warning)
        return report

    def test_failed_injury_run_warns_and_names_last_good_run(self):
        def change(ops):
            runs = self.injury(ops)["runs"]
            runs.insert(0, {"created_at": "2026-11-06T14:00:00Z", "event": "workflow_dispatch",
                            "conclusion": "failure", "health": "failed", "summary": {"mode": "LIVE"}})
        self.edit(change)
        report = self.assert_degraded_but_ready("not healthy")
        self.assertEqual(report["checks"]["injury-pull.yml"]["last_good_age_hours"], 1.0)

    def test_missing_injury_evidence_warns(self):
        self.edit(lambda ops: ops.__setitem__("workflow_health",
                  [w for w in ops["workflow_health"] if w["file"] != "injury-pull.yml"]))
        report = self.assert_degraded_but_ready("no injury producer evidence")
        self.assertIsNone(report["checks"]["injury-pull.yml"]["last_good_age_hours"])

    def test_stale_injury_run_warns(self):
        self.edit(lambda ops: self.injury(ops)["runs"][0].__setitem__("created_at", "2026-11-06T08:00:00Z"))
        self.assert_degraded_but_ready("old")

    def test_healthy_injury_run_is_not_degraded(self):
        result, report = self.run_gate()
        self.assertTrue(report["ready"])
        self.assertEqual(report["degraded"], [])
        self.assertEqual(report["checks"]["injury-pull.yml"]["status"], "ok")

    def test_other_producers_still_fail_closed(self):
        self.edit(lambda ops: next(w for w in ops["workflow_health"] if w["file"] == "picks.yml")
                  ["runs"][0].__setitem__("conclusion", "failure"))
        result, report = self.run_gate()
        self.assertEqual(result.returncode, 1)
        self.assertTrue(any("picks.yml" in e for e in report["errors"]))


if __name__ == "__main__":
    unittest.main()
