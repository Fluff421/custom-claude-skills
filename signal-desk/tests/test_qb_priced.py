"""Factors v5: a QB absence the line already reflects adds nothing; a new one counts but caps the pick at Lean."""
import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import factors as fx  # noqa: E402
import situational as sit  # noqa: E402
import context_sync as cs  # noqa: E402
import picks  # noqa: E402
import markets  # noqa: E402

norm = lambda x: "".join(c for c in x.lower() if c.isalnum())  # noqa: E731
TODAY = dt.date(2026, 11, 2)
BASE = {"League": "NFL", "Home Team": "H", "Away Team": "A", "Home FPI": 0.0, "Away FPI": 0.0, "HFA": 2.0,
        "Vegas Implied Home Margin": 2.0, "Injury Notes": "AWAY: none listed | HOME: none listed"}
OUT = "HOME QB OUT Jalen Hurts -> Tanner McKee [verified 2026-11-02] | AWAY QB PLAYING J.J. McCarthy [verified 2026-11-02]"
P = {"sigma": 12.5, "lean": 1.0, "strong": 2.5, "max": 4.0,
     "units": {"Lean": 0.5, "Strong Play": 1.5, "Max Play": 3.0}, "multipliers": {}}


class Annotate(unittest.TestCase):
    def test_replacement_led_passing_is_priced(self):
        n = sit.annotate_priced(OUT, {"home": ("Tanner McKee", "2026-11-01")}, norm)
        self.assertIn("HOME QB OUT Jalen Hurts -> Tanner McKee [verified 2026-11-02] [priced: Tanner McKee led passing 2026-11-01]", n)
        self.assertEqual(sit.qb_priced(n), {"home": "Tanner McKee led passing 2026-11-01"})
        self.assertEqual(sit.qb_fractions(n), {"home": 1.0, "away": 0.0})  # the note still says OUT

    def test_starter_led_passing_is_new(self):
        n = sit.annotate_priced(OUT, {"home": ("Jalen Hurts", "2026-11-01")}, norm)
        self.assertEqual(n, OUT)
        self.assertEqual(sit.qb_priced(n), {})

    def test_playing_side_never_tagged_and_idempotent(self):
        n = sit.annotate_priced(OUT, {"home": ("Tanner McKee", "2026-11-01"), "away": ("Jameis Winston", "2026-11-01")}, norm)
        self.assertNotIn("AWAY QB PLAYING J.J. McCarthy [verified 2026-11-02] [priced", n)
        self.assertEqual(sit.annotate_priced(n, {"home": ("Tanner McKee", "2026-11-01")}, norm), n)

    def test_unknown_passer_leaves_note(self):
        self.assertEqual(sit.annotate_priced(OUT, {}, norm), OUT)


class LeadingPasser(unittest.TestCase):
    SUMMARY = {"boxscore": {"players": [
        {"team": {"id": "33"}, "statistics": [{"name": "passing", "labels": ["C/ATT", "YDS"], "athletes": [
            {"athlete": {"displayName": "Joe Fagnano"}, "stats": ["10/21", "91"]},
            {"athlete": {"displayName": "Lamar Jackson"}, "stats": ["0/1", "0"]},
            {"athlete": {"displayName": "Tyler Huntley"}, "stats": ["2/4", "0"]}]}]},
        {"team": {"id": "2"}, "statistics": [{"name": "passing", "labels": ["C/ATT"], "athletes": [
            {"athlete": {"displayName": "Josh Allen"}, "stats": ["21/34"]}]}]}]}}

    def test_most_attempts_for_that_team(self):
        self.assertEqual(cs.leading_passer(self.SUMMARY, "33"), "Joe Fagnano")
        self.assertEqual(cs.leading_passer(self.SUMMARY, "2"), "Josh Allen")
        self.assertEqual(cs.leading_passer(self.SUMMARY, "99"), "")
        self.assertEqual(cs.leading_passer({}, "33"), "")


class Factors(unittest.TestCase):
    def test_priced_absence_adds_no_points(self):
        new = fx.compute({**BASE, "QB Starter Note": OUT}, TODAY, "now")["detail"]
        self.assertGreaterEqual(new["home_inj_pts"], 4.0)
        self.assertEqual(new["qb_out_new"], {"home": 1.0})
        priced = sit.annotate_priced(OUT, {"home": ("Tanner McKee", "2026-11-01")}, norm)
        d = fx.compute({**BASE, "QB Starter Note": priced}, TODAY, "now")["detail"]
        self.assertEqual(d["home_inj_pts"], 0.0)
        self.assertEqual(d["qb_out_new"], {})
        self.assertIn("home", d["qb_priced"])
        self.assertEqual(d["qb_unverified"], {})  # a starter check exists, so no unverified cap either


class Caps(unittest.TestCase):
    def setUp(self):
        self.old = picks.FACTOR_MODE
        picks.FACTOR_MODE = "live"

    def tearDown(self):
        picks.FACTOR_MODE = self.old

    def test_new_absence_capped_at_lean(self):
        f = {**BASE, "Home FPI": 0.0, "Away FPI": 2.0, "Vegas Implied Home Margin": 1.0, "QB Starter Note": OUT}
        new, edge, tier, prob, units = picks.evaluate(f, P, {}, "now")
        self.assertLessEqual(edge, -4.0)  # would be Max Play on the away side
        self.assertEqual(tier, "Lean")
        self.assertIn("new QB absence (home): Max Play capped at Lean", new["Sharp-Sheet Data Completeness"])

    def test_priced_absence_not_capped_and_edge_shrinks(self):
        f = {**BASE, "Home FPI": 0.0, "Away FPI": 2.0, "Vegas Implied Home Margin": 1.0,
             "QB Starter Note": sit.annotate_priced(OUT, {"home": ("Tanner McKee", "2026-11-01")}, norm)}
        new, edge, tier, prob, units = picks.evaluate(f, P, {}, "now")
        self.assertAlmostEqual(edge, -1.0, places=1)
        self.assertEqual(tier, "Lean")
        self.assertNotIn("new QB absence", new["Sharp-Sheet Data Completeness"])

    def test_cap_switch_off(self):
        old = picks.QB_OUT_NEW_CAP
        picks.QB_OUT_NEW_CAP = False
        try:
            f = {**BASE, "Home FPI": 0.0, "Away FPI": 2.0, "Vegas Implied Home Margin": 1.0, "QB Starter Note": OUT}
            self.assertEqual(picks.evaluate(f, P, {}, "now")[2], "Max Play")
        finally:
            picks.QB_OUT_NEW_CAP = old


class Markets(unittest.TestCase):
    def test_total_skips_priced_side_and_caps_new(self):
        p = {"total_weather_pts": 3.0, "total_qb_out_pts": 1.5, "total_injury_pts": 0.15}
        pts, why = markets.total_factor_points({"QB Starter Note": OUT}, p)
        self.assertAlmostEqual(pts, -1.5)
        priced = sit.annotate_priced(OUT, {"home": ("Tanner McKee", "2026-11-01")}, norm)
        pts, why = markets.total_factor_points({"QB Starter Note": priced}, p)
        self.assertEqual(pts, 0.0)
        f = {"Factor Detail": '{"qb_out_new": {"home": 1.0}}'}
        self.assertEqual(markets.qb_new_cap("Strong Play", f), "Lean")
        self.assertEqual(markets.qb_new_cap("Lean", f), "Lean")
        self.assertEqual(markets.qb_new_cap("Max Play", {"Factor Detail": '{"qb_out_new": {}}'}), "Max Play")


if __name__ == "__main__":
    unittest.main()
