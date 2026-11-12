import datetime as dt
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ops_export as ops


class ObservationHealth(unittest.TestCase):
    def observe_picks(self, runs):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("1_picks.txt", "Mode: LIVE\nNew picks: 0\n")
        with patch.object(ops, "gh_json", return_value={"workflow_runs": runs}), \
                patch.object(ops, "gh_logs_zip", return_value=archive.getvalue()):
            health = ops.workflow_health("example/repo", "test-token",
                                         dt.datetime(2026, 11, 6, 14, tzinfo=dt.timezone.utc))
        return next(w for w in health if w["file"] == "picks.yml")

    def test_skipped_chain_is_observed_but_not_misreported_as_a_producer(self):
        base = {"event": "workflow_run", "head_branch": "main", "html_url": "https://github.com/example/run"}
        skipped = dict(base, id=2, created_at="2026-11-06T13:40:00Z", conclusion="skipped")
        healthy = dict(base, id=1, created_at="2026-11-06T13:30:00Z", conclusion="success")
        observed = self.observe_picks([skipped, healthy])
        self.assertEqual(observed["latest_health"], "ok")
        self.assertEqual([r["run_id"] for r in observed["runs"]], [1])
        self.assertEqual(observed["skipped_chains"][0]["run_id"], 2)
        self.assertEqual(self.observe_picks([skipped])["latest_health"], "no_runs_in_window")

    def test_actual_failed_or_scheduled_skipped_run_still_supersedes_success(self):
        base = {"event": "workflow_run", "head_branch": "main", "html_url": "https://github.com/example/run"}
        healthy = dict(base, id=1, created_at="2026-11-06T13:30:00Z", conclusion="success")
        for event, conclusion in (("workflow_run", "failure"), ("schedule", "skipped"),
                                  ("workflow_dispatch", "skipped"), ("workflow_run", "cancelled")):
            with self.subTest(event=event, conclusion=conclusion):
                failed = dict(base, id=2, created_at="2026-11-06T13:40:00Z",
                              event=event, conclusion=conclusion)
                observed = self.observe_picks([failed, healthy])
                self.assertNotEqual(observed["latest_health"], "ok")
                self.assertEqual(observed["runs"][0]["run_id"], 2)

    def test_successful_injury_log_with_partial_replacement_coverage_is_degraded(self):
        info = ops.parse_log("Mode: LIVE\nReplacement games expected: 2\nReplacement games covered: 1\n")
        state, reasons = ops.judge("NCAAF Injury Pull", "success", info)
        self.assertEqual(state, "degraded")
        self.assertIn("replacement injury coverage is incomplete", reasons)

    def test_injury_games_labelled_by_source_schedule_are_accounted_for(self):
        log = ("Mode: LIVE\nReplacement games expected: 61\nReplacement games covered: 4\n"
               "Replacement games with official report not yet due: 34\n"
               "Replacement games with official report overdue: 22\n"
               "Replacement games with an independent program (no official report): 1\n")
        state, reasons = ops.judge("NCAAF Injury Pull", "success", ops.parse_log(log))
        self.assertEqual((state, reasons), ("ok", []))
        short = log.replace("overdue: 22", "overdue: 21")
        state, reasons = ops.judge("NCAAF Injury Pull", "success", ops.parse_log(short))
        self.assertEqual(state, "degraded")
        self.assertIn("replacement injury coverage is incomplete", reasons)

    def test_chained_main_pick_refresh_counts_as_production_evidence(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("1_picks.txt", "Mode: LIVE\nNew picks: 0\n")
        run = {"id": 12, "event": "workflow_run", "head_branch": "main",
               "created_at": "2026-11-06T13:30:00Z", "conclusion": "success",
               "html_url": "https://github.com/example/actions/runs/12"}
        with patch.object(ops, "gh_json", return_value={"workflow_runs": [run]}), \
                patch.object(ops, "gh_logs_zip", return_value=archive.getvalue()):
            health = ops.workflow_health("example/repo", "test-token",
                                         dt.datetime(2026, 11, 6, 14, tzinfo=dt.timezone.utc))
        picks = next(w for w in health if w["file"] == "picks.yml")
        self.assertEqual(picks["latest_health"], "ok")
        self.assertEqual(picks["runs"][0]["run_id"], 12)

    def test_fresh_matching_observation_clears_timestamp_only_staleness(self):
        now = dt.datetime(2026, 11, 6, 14, tzinfo=dt.timezone.utc)
        rows = [{"id": "game1", "fields": {"Date": "2026-11-07", "ESPN Event ID": "event1",
                 "ESPN Pulled At": "2026-11-05T14:00Z"}}]
        beat = {"game1": {"event_id": "event1", "checked_at": "2026-11-06T13:30Z"}}
        key = "upcoming_espn_data_stale"
        self.assertEqual(ops.row_health(rows, now.date(), now, {})["checks"][key]["count"], 1)
        self.assertEqual(ops.row_health(rows, now.date(), now, beat)["checks"][key]["count"], 0)
        beat["game1"]["event_id"] = "different-event"
        self.assertEqual(ops.row_health(rows, now.date(), now, beat)["checks"][key]["count"], 1)

    def test_partial_injury_success_is_classified_as_degraded(self):
        info = ops.parse_log("Mode: LIVE\nRows updated: 2\nWARN: DraftEdge parsed only 0 rows; treated as failed\n")
        self.assertEqual(ops.judge("NCAAF Injury Pull", "success", info)[0], "degraded")

    def test_missing_or_future_observation_does_not_appear_fresh(self):
        now = dt.datetime(2026, 11, 6, 14, tzinfo=dt.timezone.utc)
        row = {"id": "game1", "fields": {"Date": "2026-11-07", "ESPN Event ID": "event1"}}
        for stamp in (None, "not-a-date", "2026-11-07T14:00Z"):
            row["fields"]["ESPN Pulled At"] = stamp
            health = ops.row_health([row], now.date(), now, {})
            self.assertEqual(health["checks"]["upcoming_espn_data_stale"]["count"], 1)
