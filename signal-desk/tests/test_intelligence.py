import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import intelligence_report as ir  # noqa: E402
import splash_compare as sc  # noqa: E402

GAMES = [
    {"_id": "r1", "Game": "Kansas State @ Colorado", "Date": "2026-11-07", "League": "NCAAF", "Home Team": "Colorado", "Away Team": "Kansas State",
     "Recommended Side": "Kansas State +1.5 (spread)", "Sharp-Sheet Tier": "Lean", "Sharp-Sheet Suggested Units": 0.5, "Vegas Implied Home Margin": 1.5, "Adj Edge": -1.0},
    {"_id": "r2", "Game": "Auburn @ Ole Miss", "Date": "2026-11-07", "League": "NCAAF", "Home Team": "Ole Miss", "Away Team": "Auburn",
     "Recommended Side": "Auburn +10.5 (spread)", "Sharp-Sheet Tier": "Strong Play", "Vegas Implied Home Margin": 10.5, "Adj Edge": -3.0},
    {"_id": "r3", "Game": "Alabama @ LSU", "Date": "2026-11-08", "League": "NCAAF", "Home Team": "LSU", "Away Team": "Alabama", "Vegas Implied Home Margin": -3.0},
]


class Splash(unittest.TestCase):
    def test_parse(self):
        picks, bad = sc.parse_lines("Alabama -7.5\n- Ole Miss +3 \n3) Kansas State PK\nnonsense here\n\n")
        self.assertEqual([(p["team"], p["line"]) for p in picks], [("Alabama", -7.5), ("Ole Miss", 3.0), ("Kansas State", 0.0)])
        self.assertEqual(bad, ["nonsense here"])

    def test_match_and_against(self):
        picks, _ = sc.parse_lines("Colorado -1.5\nAuburn +10.5\nAlabama +3\nTexas -4")
        rows, unmatched = sc.compare(picks, GAMES, "now")
        by = {r["game"]: r for r in rows}
        self.assertEqual(by["Kansas State @ Colorado"]["matched"], "no")      # model on K-State, user on Colorado
        self.assertEqual(by["Auburn @ Ole Miss"]["matched"], "yes")
        self.assertEqual(by["Alabama @ LSU"]["matched"], "no model pick")
        self.assertEqual(by["Auburn @ Ole Miss"]["splash_line_in_ledger"], 10.5)
        self.assertEqual(unmatched, ["Texas -4"])

    def test_render_lists_passes(self):
        picks, _ = sc.parse_lines("Auburn +10.5")
        rows, un = sc.compare(picks, GAMES, "now")
        text = sc.render(rows, un, [], [GAMES[0]], "now")
        self.assertIn("matched", text)
        self.assertIn("you did not pick", text)
        self.assertIn("Kansas State +1.5", text)


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
