import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import clv_learning as cl  # noqa: E402
import picks  # noqa: E402


def row(tier, clv, grade="Win", **kw):
    return {"Sharp-Sheet Tier": tier, "Sharp-Sheet CLV Points": clv, "Grade": grade, **kw}


class Gate(unittest.TestCase):
    def test_earned_needs_mean_minus_se_positive(self):
        g = cl.unit_gate([row("Strong Play", 1.0 + (0.5 if i % 2 else -0.5)) for i in range(20)])
        self.assertEqual(g["Strong Play"]["status"], "earned")

    def test_not_earning_when_mean_nonpositive(self):
        g = cl.unit_gate([row("Max Play", -0.5 if i % 2 else 0.25) for i in range(24)])
        self.assertEqual(g["Max Play"]["status"], "not earning")

    def test_unproven_below_sample(self):
        g = cl.unit_gate([row("Lean", 2.0) for _ in range(19)])
        self.assertEqual(g["Lean"]["status"], "unproven")

    def test_noisy_positive_stays_unproven(self):
        g = cl.unit_gate([row("Lean", 0.1 + (3.0 if i % 2 else -3.0)) for i in range(30)])
        self.assertEqual(g["Lean"]["status"], "unproven")

    def test_gated_units(self):
        gate = {"Max Play": {"status": "earned"}, "Strong Play": {"status": "not earning"}}
        self.assertEqual(cl.gated_units(3.0, "Max Play", gate, 1.0), (3.0, "earned"))
        self.assertEqual(cl.gated_units(1.5, "Strong Play", gate, 1.0), (0.5, "not earning"))
        self.assertEqual(cl.gated_units(3.0, "Lean", gate, 1.0), (1.0, "unproven"))
        self.assertEqual(cl.gated_units(3.0, "Max Play", None, 1.0), (1.0, "unproven"))


def game(clv, side_home, edge_home, inj_toward_home=0.0, rest=0.0):
    hf = 10.0 + edge_home
    detail = {"home_inj_pts": 0.0, "away_inj_pts": inj_toward_home,
              "situ_parts": {"lookahead": 0.0, "rest": rest, "travel": 0.0, "revenge": 0.0, "weather": 0.0}}
    return {"League": "NCAAF", "Home Team": "HOME", "Away Team": "AWAY", "Home FPI": hf, "Away FPI": 10.0, "HFA": 0.0,
            "Vegas Implied Home Margin": 0.0, "Recommended Side": f"{'HOME' if side_home else 'AWAY'} -1 (spread)",
            "Sharp-Sheet CLV Points": clv, "Grade": "Win", "Factor Detail": json.dumps(detail)}


class Model(unittest.TestCase):
    def test_features_signed_to_pick_side(self):
        x = cl.features(3.0, {"home_inj_pts": 1.0, "away_inj_pts": 2.0, "situ_parts": {"rest": 0.5}}, -1)
        self.assertEqual(x["edge"], -3.0)
        self.assertEqual(x["inj"], -1.0)
        self.assertEqual(x["rest"], -0.5)

    def test_below_minimum_uses_history_prior(self):
        m = cl.fit([game(0.5, True, 3.0)] * 5, "NCAAF", hist={"slope": 0.1, "se": 0.01, "n": 1000})
        self.assertFalse(m["ok"])
        self.assertEqual(m["coef"]["edge"], 0.1)
        self.assertEqual(m["coef"]["inj"], 0.0)

    def test_learns_injury_signal(self):
        fs = []
        for i in range(60):
            inj = 2.0 if i % 3 == 0 else 0.0
            fs.append(game(0.1 + 0.6 * inj + (0.2 if i % 2 else -0.2), True, 2.0, inj_toward_home=inj))
        m = cl.fit(fs, "NCAAF", hist={"slope": 0.05, "se": 0.01, "n": 1000})
        self.assertTrue(m["ok"])
        self.assertGreater(m["coef"]["inj"], 0.3)
        self.assertEqual(m["coef"]["rest"], 0.0)   # never non-zero: not fitted
        self.assertGreater(cl.predict(m, 2.0, {"away_inj_pts": 2.0, "home_inj_pts": 0.0}, 1), 1.0)

    def test_clv_tier(self):
        self.assertEqual(cl.clv_tier(0.1), "No Play")
        self.assertEqual(cl.clv_tier(0.3), "Lean")
        self.assertEqual(cl.clv_tier(0.7), "Strong Play")
        self.assertEqual(cl.clv_tier(1.2), "Max Play")


class Shadow(unittest.TestCase):
    def test_append_only_and_forward_check(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.csv")
            cl.append_shadow([{"record_id": f"r{i}", "pred_clv": i * 0.1} for i in range(40)], p)
            cl.append_shadow([{"record_id": "r1", "pred_clv": 9.9}], p)   # later re-log of r1 is ignored
            with open(p) as fh:
                self.assertEqual(len(fh.readlines()), 42)
            fwd = cl.forward_check({f"r{i}": i * 0.1 + (0.05 if i % 2 else -0.05) for i in range(40)}, p)
            self.assertEqual(fwd["n"], 40)
            self.assertGreater(fwd["corr"], 0.9)
            self.assertTrue(fwd["ready"])
            self.assertFalse(cl.forward_check({"r1": 1.0}, p)["ready"])


class PicksIntegration(unittest.TestCase):
    P = {"sigma": 15.0, "lean": 1.0, "strong": 2.5, "max": 4.0,
         "units": {"Lean": 0.5, "Strong Play": 1.5, "Max Play": 3.0}, "multipliers": {}}
    F = {"League": "NCAAF", "Home Team": "HOME", "Away Team": "AWAY", "Home FPI": 15.0, "Away FPI": 10.0, "HFA": 0.0,
         "Vegas Implied Home Margin": 0.0}

    def setUp(self):
        self._old = dict(picks.CLV_PARAMS)

    def tearDown(self):
        picks.CLV_PARAMS.clear()
        picks.CLV_PARAMS.update(self._old)

    def test_units_follow_clv_gate(self):
        picks.CLV_PARAMS.clear()
        picks.CLV_PARAMS["NCAAF"] = {"gate": {"Max Play": {"status": "earned"}}}
        self.assertEqual(picks.capped_units(3.0, "NCAAF", "Max Play", {}), 3.0)
        picks.CLV_PARAMS["NCAAF"] = {"gate": {"Max Play": {"status": "not earning"}}}
        self.assertEqual(picks.capped_units(3.0, "NCAAF", "Max Play", {}), 0.5)
        picks.CLV_PARAMS.clear()
        self.assertEqual(picks.capped_units(3.0, "NCAAF", "Max Play", {("NCAAF", "Max Play"): 50}), 1.0)

    def test_shadow_note_does_not_change_tier(self):
        picks.CLV_PARAMS.clear()
        picks.CLV_PARAMS["NCAAF"] = {"model": {"ok": True, "n": 40, "coef": {"edge": 0.0}}}
        new, edge, tier, prob, units = picks.evaluate(self.F, self.P, {}, "now")
        self.assertEqual(tier, "Max Play")
        self.assertIn("pCLV +0.00 (CLV tier No Play, shadow)", new["Sharp-Sheet Data Completeness"])
        self.assertEqual(picks.LAST_CLV["clv_tier"], "No Play")


if __name__ == "__main__":
    unittest.main()
