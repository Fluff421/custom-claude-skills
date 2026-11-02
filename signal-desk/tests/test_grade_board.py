import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import grade_board as g  # noqa: E402


class OpenFilter(unittest.TestCase):
    def test_status_no_bet_is_excluded(self):
        self.assertIn("{Status}!='No bet'", g.OPEN_FORMULA)
        self.assertIn("{Status}!='Graded'", g.OPEN_FORMULA)


class KickoffDates(unittest.TestCase):
    def test_text_kickoff_padded(self):
        self.assertEqual(g.kickoff_dates({"Kickoff": "2026-09-22 8:15 PM EDT"}), ["20260921", "20260922", "20260923"])

    def test_utc_kickoff_preferred(self):
        self.assertEqual(g.kickoff_dates({"Kickoff UTC": "2026-09-20T00:30:00.000Z", "Kickoff": "2026-09-19 8:30 PM EDT"})[1], "20260920")

    def test_missing_or_bad(self):
        self.assertEqual(g.kickoff_dates({}), [])
        self.assertEqual(g.kickoff_dates({"Kickoff": "Sat night"}), [])


class Aliases(unittest.TestCase):
    def test_board_labels_match_espn(self):
        for board, espn in (("GSU", "GAST"), ("NCST", "NCSU"), ("RUT", "RUTG"), ("MERC", "MER"), ("MISS", "MISS"), ("WSH", "WAS")):
            self.assertTrue(g.same_team(board, espn), (board, espn))

    def test_no_false_match(self):
        self.assertFalse(g.same_team("GSU", "GASO"))
        self.assertFalse(g.same_team("NCST", "UNC"))


class LeagueScope(unittest.TestCase):
    def test_rows_only_see_their_league(self):
        nfl, cfb = [{"away": "BUF"}], [{"away": "BUFF"}]
        self.assertIs(g.league_finals({"League": "NFL"}, nfl, cfb), nfl)
        self.assertIs(g.league_finals({"League": "NCAAF"}, nfl, cfb), cfb)
        self.assertEqual(len(g.league_finals({}, nfl, cfb)), 2)


if __name__ == "__main__":
    unittest.main()
