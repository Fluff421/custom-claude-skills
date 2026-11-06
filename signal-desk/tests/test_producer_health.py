import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import producer_health as ph


class ProducerHealth(unittest.TestCase):
    def test_partial_feed_is_nonzero_but_no_games_is_not_a_dropout(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "health.json"
            with self.assertRaises(SystemExit) as raised:
                ph.finish("injury", ["DraftEdge unavailable"], path=path)
            self.assertEqual(raised.exception.code, 1)
            self.assertEqual(json.loads(path.read_text())["status"], "degraded")
            ph.finish("injury", [], path=path, no_games=True)
            self.assertEqual(json.loads(path.read_text())["status"], "no_games")

    def test_unchanged_record_gets_checked_at_without_changing_changed_at(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "heartbeats.json"
            ph.record_checks([("game1", "event1", True)], "2026-11-06T12:00:00Z", path)
            ph.record_checks([("game1", "event1", False)], "2026-11-06T13:00:00Z", path)
            record = json.loads(path.read_text())["records"]["game1"]
            self.assertEqual(record["checked_at"], "2026-11-06T13:00:00Z")
            self.assertEqual(record["changed_at"], "2026-11-06T12:00:00Z")
