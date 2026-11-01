import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import intelligence_report as ir  # noqa: E402

GAMES = [
    {"_id": "r1", "Game": "Kansas State @ Colorado", "Date": "2026-11-07", "League": "NCAAF", "Home Team": "Colorado", "Away Team": "Kansas State",
     "Recommended Side": "Kansas State +1.5 (spread)", "Sharp-Sheet Tier": "Lean", "Sharp-Sheet Suggested Units": 0.5, "Vegas Implied Home Margin": 1.5, "Adj Edge": -1.0},
    {"_id": "r2", "Game": "Auburn @ Ole Miss", "Date": "2026-11-07", "League": "NCAAF", "Home Team": "Ole Miss", "Away Team": "Auburn",
     "Recommended Side": "Auburn +10.5 (spread)", "Sharp-Sheet Tier": "Strong Play", "Vegas Implied Home Margin": 10.5, "Adj Edge": -3.0},
    {"_id": "r3", "Game": "Alabama @ LSU", "Date": "2026-11-08", "League": "NCAAF", "Home Team": "LSU", "Away Team": "Alabama", "Vegas Implied Home Margin": -3.0},
]


class Explain(unittest.TestCase):
    def test_result_explanation_names_helping_and_hurting_factors(self):
        f = {"Game": "A @ B", "Home Team": "B", "Away Team": "A", "League": "NFL", "Home FPI": 5, "Away FPI": 3, "HFA": 2, "Actual Home Margin": 10,
             "Vegas Implied Home Margin": 3, "Recommended Side": "B -3 (spread)", "Grade": "Win", "Sharp-Sheet Tier": "Lean",
             "Factor Detail": json.dumps({"home_inj_pts": 0, "away_inj_pts": 2.0, "situ_parts": {"rest": -0.6, "travel": 0.0}})}
        e = ir.explain_result(f)
        self.assertEqual(e["model_error"], 6.0)
        self.assertIn("injuries +2.0", e["factors_helped"])
        self.assertIn("rest -0.6", e["factors_hurt"])
        self.assertEqual(e["cover_margin"], 7.0)

    def test_old_games_without_factor_record(self):
        e = ir.explain_result({"Game": "x", "Home FPI": 1, "Away FPI": 0, "Actual Home Margin": 3, "League": "NFL"})
        self.assertTrue(any("no factor record" in n for n in e["notes"]))

    def test_brier(self):
        rows = [{"Grade": "Win", "Sharp-Sheet Est. Win Prob %": 0.6}, {"Grade": "Loss", "Sharp-Sheet Est. Win Prob %": 0.6}]
        self.assertAlmostEqual(ir.brier(rows), 0.26, places=2)


if __name__ == "__main__":
    unittest.main()
