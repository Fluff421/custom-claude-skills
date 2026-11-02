import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import sigma_learning as sg  # noqa: E402


def hist(n, resid, segs=()):
    return [(resid if i % 2 else -resid, 1.0, list(segs)) for i in range(n)]


class Learn(unittest.TestCase):
    def test_reset_when_current_out_of_range(self):
        r = sg.learn("NCAAF", [], 20.0, 2026, history=hist(4000, 15.0))
        self.assertAlmostEqual(r["sigma"], 15.0, places=1)
        self.assertIn("outside", r["reason"])

    def test_step_limited_inside_range(self):
        r = sg.learn("NCAAF", [], 15.0, 2026, history=hist(4000, 17.5))
        self.assertAlmostEqual(r["sigma"], 15.5, places=2)

    def test_shrinks_to_prior_with_little_data(self):
        r = sg.learn("NFL", [], None, 2026, history=hist(10, 20.0))
        self.assertLess(r["sigma"], 15.0)  # 10 games at 20 barely move a 100-game prior at 12.5 (and clip at 15)
        self.assertGreater(r["sigma"], 12.5)

    def test_no_data_returns_prior(self):
        self.assertEqual(sg.learn("NCAAF", [], None, 2026, history=[])["sigma"], 15.0)

    def test_segment_needs_minimum_and_is_bounded(self):
        rows = hist(3000, 15.0) + hist(20, 30.0, ["injury_heavy"])
        self.assertFalse(sg.learn("NCAAF", [], 15.0, 2026, history=rows)["segments"]["injury_heavy"]["applied"])
        rows = hist(3000, 15.0) + hist(400, 30.0, ["injury_heavy"])
        seg = sg.learn("NCAAF", [], 15.0, 2026, history=rows)["segments"]["injury_heavy"]
        self.assertTrue(seg["applied"])
        self.assertLessEqual(seg["mult"], sg.SEG_RANGE[1])

    def test_ledger_rows_use_locked_line_and_factor_detail(self):
        f = {"Home Score": 30, "Away Score": 10, "Vegas Implied Home Margin": 7,
             "Factor Detail": json.dumps({"home_inj_pts": 2.5, "away_inj_pts": 1.0, "home_qb_listed": True, "weather_sev": 0.8})}
        (res, w, segs), = sg.ledger_residuals([f])
        self.assertEqual(res, 13)
        self.assertEqual(set(segs), {"injury_heavy", "qb_uncertain", "weather"})


class Apply(unittest.TestCase):
    def test_clean_guards_stale_values(self):
        self.assertEqual(sg.clean("NCAAF", 20), 15.0)
        self.assertEqual(sg.clean("NCAAF", 14.9), 14.9)
        self.assertEqual(sg.clean("NFL", None), 12.5)

    def test_sigma_for_only_applied_segments(self):
        segs = {"weather": {"mult": 1.1, "applied": True}, "big_spread": {"mult": 1.2, "applied": False}}
        s, used = sg.sigma_for(15.0, 21.0, {"weather_sev": 1.0}, segs)
        self.assertAlmostEqual(s, 16.5)
        self.assertEqual(used, ["weather x1.10"])

    def test_params_file_merge(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "lp.json")
            sg.write_params({"sigma": {"NCAAF": {"sigma": 15}}}, p)
            sg.write_params({"clv": {"x": 1}}, p)
            sg.write_params({"sigma": {"NFL": {"sigma": 12.5}}}, p)
            self.assertEqual(set(sg.read_params(p)["sigma"]), {"NCAAF", "NFL"})
            self.assertIn("clv", sg.read_params(p))


if __name__ == "__main__":
    unittest.main()
