import datetime as dt
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ops_export as ops


class ObservationHealth(unittest.TestCase):
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
