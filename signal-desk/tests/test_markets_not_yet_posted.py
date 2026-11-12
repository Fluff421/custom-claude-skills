from pathlib import Path
import datetime as dt
import json
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import espn_sync as es
import markets as mk

TODAY = dt.date(2026, 11, 11)


def game(date):
    return {"_id": "rec1", "Game": "Miami (OH) @ Kent State", "League": "NCAAF", "Date": date, "ESPN Event ID": "401866466"}


class MarketNotYetPosted(unittest.TestCase):
    def setUp(self):
        es.WARNINGS.clear()
        mk.MARKETS_NOT_YET_POSTED.clear()

    def fetch(self, date, today=TODAY):
        with patch.object(es, "http_get", return_value=json.dumps({"items": []})):
            return mk.fetch_odds(game(date), today)

    def test_far_game_without_market_is_reported_not_an_error(self):
        self.assertIsNone(self.fetch("2026-11-17"))
        self.assertEqual(es.WARNINGS, [])
        self.assertEqual(mk.MARKETS_NOT_YET_POSTED, ["Miami (OH) @ Kent State (2026-11-17)"])

    def test_near_game_without_market_is_still_an_error(self):
        for date in ("2026-11-11", "2026-11-12", "2026-11-13"):
            with self.subTest(date=date):
                es.WARNINGS.clear()
                self.fetch(date)
                self.assertEqual(es.WARNINGS, ["Miami (OH) @ Kent State: odds feed has no usable market"])
        self.assertEqual(mk.MARKETS_NOT_YET_POSTED, [])

    def test_unknown_date_or_today_is_still_an_error(self):
        self.fetch("", TODAY)
        self.fetch("2026-11-17", None)
        self.assertEqual(len(es.WARNINGS), 2)
        self.assertEqual(mk.MARKETS_NOT_YET_POSTED, [])

    def test_fetch_failure_is_always_an_error(self):
        with patch.object(es, "http_get", side_effect=OSError("timeout")):
            mk.fetch_odds(game("2026-11-17"), TODAY)
        self.assertEqual(len(es.WARNINGS), 1)


if __name__ == "__main__":
    unittest.main()
