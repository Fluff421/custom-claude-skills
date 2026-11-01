import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import situational as sit  # noqa: E402
import factors as fx  # noqa: E402
import picks  # noqa: E402


def d(y, m, dd, h=18):
    return dt.datetime(y, m, dd, h, tzinfo=dt.timezone.utc)


class Situational(unittest.TestCase):
    def test_rest_days_uses_last_completed_game(self):
        games = [{"date": d(2026, 10, 24), "completed": True}, {"date": d(2026, 10, 31), "completed": True},
                 {"date": d(2026, 11, 7), "completed": False}]
        self.assertEqual(sit.rest_days(games, d(2026, 11, 7)), 7)
        self.assertEqual(sit.rest_days(games, d(2026, 11, 5)), 5)
        self.assertIsNone(sit.rest_days([], d(2026, 11, 5)))

    def test_late_kickoff_stays_on_central_date(self):
        g = [{"date": d(2026, 10, 25, 1), "completed": True}]  # 8 PM Central Oct 24
        self.assertEqual(sit.rest_days(g, d(2026, 10, 31, 18)), 7)

    def test_travel(self):
        t = sit.travel("CA", "NY")
        self.assertGreater(t["mi"], 2000)
        self.assertEqual(t["tz"], 3)
        self.assertEqual(sit.travel("OH", "OH"), {"mi": 0, "tz": 0})
        self.assertIsNone(sit.travel(None, "OH"))

    def test_points_signs(self):
        f = {"Home Rest Days": 13, "Away Rest Days": 4, "Travel Note": "AWAY 2400mi/3tz | HOME 0mi/0tz",
             "Revenge Note": "Home revenge (lost 2025-10-01 10-20)"}
        p = sit.situational_points(f, "NFL")
        self.assertGreater(p["rest"], 0)    # home rested, away short
        self.assertGreater(p["travel"], 0)  # away travelled
        self.assertGreater(p["revenge"], 0)
        away = sit.situational_points({"Revenge Note": "Away revenge (x)"}, "NCAAF")
        self.assertLess(away["revenge"], 0)

    def test_missing_context_is_zero(self):
        self.assertEqual(sum(sit.situational_points({}, "NFL").values()), 0)

    def test_revenge_only_after_a_loss(self):
        self.assertIsNone(sit.revenge_flag([]))
        self.assertIsNone(sit.revenge_flag([{"won": False, "date": "a", "score": "1-2"}, {"won": True, "date": "b", "score": "3-2"}]))
        self.assertTrue(sit.revenge_flag([{"won": True, "date": "a", "score": "3-2"}, {"won": False, "date": "b", "score": "1-2"}]))

    def test_weather_is_note_only(self):
        self.assertEqual(sit.weather_note(None, {"indoor": True}), "indoor")
        self.assertIn("40F", sit.weather_note({"temperature": 40, "conditionId": "Snow"}, {}))
        base = {"Home FPI": 10, "Away FPI": 5, "HFA": 2.5, "Vegas Implied Home Margin": 6, "League": "NCAAF"}
        a = fx.compute({**base}, dt.date(2026, 11, 1), "x")
        b = fx.compute({**base, "Weather Note": "20F, Snow"}, dt.date(2026, 11, 1), "x")
        self.assertEqual(a["adj_model"], b["adj_model"])

    def test_qb_feed_overrides_injury_list(self):
        rows = [{"team": "Ohio State", "verified": "verified", "classification": "starter_out", "starter": "A", "replacement": "B", "source_date": "2026-10-20"},
                {"team": "USC", "verified": "unverified", "classification": "starter_out", "starter": "C"}]
        note = sit.qb_note(rows, "USC", "Ohio State", lambda x: x.lower())
        self.assertIn("AWAY QB OUT A -> B", note)
        self.assertNotIn("HOME", note)
        base = {"Home FPI": 10, "Away FPI": 10, "HFA": 2.5, "Vegas Implied Home Margin": 2.5, "League": "NCAAF"}
        x = fx.compute({**base, "QB Starter Note": note}, dt.date(2026, 11, 1), "x")
        self.assertGreater(x["inj_adj"], 3.0)  # away QB out helps home
        self.assertTrue(x["detail"]["inj_parsed"])


class AllGames(unittest.TestCase):
    P = {"sigma": 14.0, "lean": 1.0, "strong": 2.5, "max": 4.0, "units": {"Lean": 0.5, "Strong Play": 1.0, "Max Play": 1.5}, "multipliers": {}}
    F = {"League": "NCAAF", "Home FPI": 10, "Away FPI": 10, "HFA": 2.5, "Vegas Implied Home Margin": 2.0, "Home Team": "H", "Away Team": "A"}

    def test_tiny_edge_gets_zero_unit_tracking_pick(self):
        new, edge, tier, prob, units = picks.evaluate(self.F, self.P, {}, "now")
        self.assertIsNotNone(new)
        self.assertEqual(tier, "No Play")
        self.assertEqual(units, 0.0)
        self.assertEqual(new["Sharp-Sheet Suggested Units"], 0.0)
        self.assertIn("Tracking pick", new["Sharp-Sheet Data Completeness"])
        self.assertGreaterEqual(prob, 0.5)

    def test_real_edge_unchanged(self):
        new, edge, tier, prob, units = picks.evaluate({**self.F, "Vegas Implied Home Margin": -3.0}, self.P, {}, "now")
        self.assertEqual(tier, "Max Play")
        self.assertGreater(units, 0)


if __name__ == "__main__":
    unittest.main()
