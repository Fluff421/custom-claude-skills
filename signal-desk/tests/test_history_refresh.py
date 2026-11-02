import csv
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import history_backfill as hb  # noqa: E402


class Refresh(unittest.TestCase):
    def test_appends_only_new_finals_and_keeps_old_rows(self):
        with tempfile.TemporaryDirectory() as d:
            old_out, old_games, old_enrich = hb.OUT, hb.games, hb.enrich
            try:
                hb.OUT = d
                p = os.path.join(d, "nfl_2026.csv")
                with open(p, "w", newline="") as fh:
                    w = csv.DictWriter(fh, fieldnames=hb.COLS)
                    w.writeheader()
                    w.writerow({"league": "NFL", "event_id": "1", "kickoff_utc": "2026-10-01", "fpi_home_win_pct": "60"})
                hb.games = lambda lg, s: [{"league": lg, "event_id": "1", "kickoff_utc": "2026-10-01"},
                                          {"league": lg, "event_id": "2", "kickoff_utc": "2026-11-01"}] if lg == "NFL" else []
                hb.enrich = lambda g: {**g, "fpi_home_win_pct": "99"}
                hb.refresh(2026)
                rows = list(csv.DictReader(open(p)))
                self.assertEqual([r["event_id"] for r in rows], ["1", "2"])
                self.assertEqual(rows[0]["fpi_home_win_pct"], "60")   # first capture is never rewritten
                self.assertEqual(rows[1]["fpi_home_win_pct"], "99")
            finally:
                hb.OUT, hb.games, hb.enrich = old_out, old_games, old_enrich


if __name__ == "__main__":
    unittest.main()
