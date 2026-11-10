import datetime as dt
import os
import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import close_grade as cg
import producer_health as ph


class ImportedTotal(unittest.TestCase):
    def capture(self, total):
        now = dt.datetime.now(dt.timezone.utc)
        f = {"Date": now.date().isoformat(), "League": "NFL", "ESPN Event ID": "event",
             "Home Team": "Chicago Bears", "Away Team": "Tampa Bay Buccaneers",
             "Game": "Tampa Bay Buccaneers @ Chicago Bears"}
        if total is not None:
            f["Over/Under Line"] = total
        event = {"id": "event", "date": (now + dt.timedelta(minutes=30)).isoformat(),
                 "status": {"type": {"state": "pre", "completed": False}}}
        calls = []

        def fetch(table, *args):
            calls.append(table)
            return [{"id": "record", "fields": f}] if len(calls) == 1 else []

        with mock.patch.dict(os.environ, {"AIRTABLE_TOKEN": "test", "AIRTABLE_BASE_ID": "test",
                                         "WEBSCRAPING_AI_API_KEY": "test", "CLOSE_GRADE_LIVE": "1"}), \
             mock.patch.object(cg, "at_list_all", side_effect=fetch), \
             mock.patch.object(cg, "at_write") as write, \
             mock.patch.object(cg.es, "espn_events", return_value=[event]), \
             mock.patch.object(cg.es, "competitors", return_value={"home": {"abbreviation": "CHI"},
                               "away": {"abbreviation": "TB"}, "comp": {}}), \
             mock.patch.object(cg.es, "home_spread", return_value=(-6.5, 49.5, "test")), \
             mock.patch.object(ph, "finish"):
            cg.main()
            return write.call_args_list[0].args[1][0]["fields"]

    def test_filled_early_total_is_not_overwritten_by_espn_close(self):
        self.assertNotIn("Over/Under Line", self.capture(47.5))

    def test_blank_total_can_still_be_captured(self):
        self.assertEqual(self.capture(None)["Over/Under Line"], 49.5)

    def test_zero_is_a_value_not_blank(self):
        self.assertNotIn("Over/Under Line", self.capture(0))

if __name__ == "__main__":
    unittest.main()
