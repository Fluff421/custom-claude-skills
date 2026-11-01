import json
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import factor_learning as fl  # noqa: E402


def make(n, k_true=0.0, s_true=1.0, seed=1, with_factors=True):
    rnd = random.Random(seed)
    rows = []
    for _ in range(n):
        model = rnd.uniform(-10, 10)
        vegas = rnd.uniform(-10, 10)
        inj = rnd.uniform(-4, 4)
        actual = vegas + k_true * (model - vegas) + rnd.gauss(0, 14)
        # make injuries explain part of (actual - model) with true scale s_true
        actual += (s_true * inj) if with_factors else 0.0
        f = {"Home Score": 30 + max(actual, 0), "Away Score": 30 + max(-actual, 0), "Home FPI": model, "Away FPI": 0, "HFA": 0,
             "Vegas Implied Home Margin": vegas, "League": "NCAAF"}
        if with_factors:
            f["Factor Detail"] = json.dumps({"home_inj_pts": 0, "away_inj_pts": inj, "lookahead": {}, "situ_points": 1.0, "inj_parsed": True})
        rows.append(f)
    return rows


class Learning(unittest.TestCase):
    def test_gate_below_minimum(self):
        rows = fl.game_rows(make(10))
        self.assertFalse(fl.market_blend(rows)["ok"])
        self.assertFalse(fl.factor_scales(rows)["ok"])

    def test_market_blend_pure_noise_is_near_zero(self):
        mb = fl.market_blend(fl.game_rows(make(400, k_true=0.0)))
        self.assertTrue(mb["ok"])
        self.assertLess(mb["k"], 0.15)

    def test_market_blend_recovers_signal(self):
        mb = fl.market_blend(fl.game_rows(make(2000, k_true=0.6)))
        self.assertGreater(mb["k"], 0.5)
        self.assertLessEqual(mb["k"], 1.0)

    def test_scale_shrinks_to_prior_with_little_data_and_learns_with_more(self):
        small = fl.factor_scales(fl.game_rows(make(35, s_true=0.0, seed=3)))
        big = fl.factor_scales(fl.game_rows(make(3000, s_true=0.0, seed=4)))
        self.assertTrue(small["ok"] and big["ok"])
        self.assertGreater(small["scale_inj"], big["scale_inj"])  # little data stays closer to the 1.0 prior
        self.assertLess(big["scale_inj"], 0.2)

    def test_scorecard_prefers_true_factors(self):
        sc = fl.scorecard(fl.game_rows(make(2000, s_true=2.5, seed=5)))
        self.assertLess(sc["rmse_adjusted"], sc["rmse_base"])
        self.assertTrue(sc["ready_for_review"])

    def test_rows_without_factors_are_ignored_for_scales(self):
        self.assertFalse(fl.factor_scales(fl.game_rows(make(100, with_factors=False)))["ok"])

    def test_clip(self):
        mb = fl.market_blend(fl.game_rows(make(500, k_true=-2.0, seed=6)))
        self.assertGreaterEqual(mb["k"], 0.0)


if __name__ == "__main__":
    unittest.main()
