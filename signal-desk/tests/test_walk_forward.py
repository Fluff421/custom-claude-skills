import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import walk_forward as wf  # noqa: E402


def game(season, week, margin, line, model, kick=None):
    g = {"league": "NCAAF", "season": season, "season_type": 2, "week": week, "kick": kick or f"{season}-09-{week:02d}T18:00Z",
         "margin": margin, "line": line, "open": line, "model": model, "conf": True, "pm": ""}
    g["edge"] = model - line
    g["wk"] = (season, 2, week)
    return g


class NoLookahead(unittest.TestCase):
    def test_week_params_ignore_same_and_future_weeks(self):
        base = [game(2022, w, 10 if w % 2 else -10, 0.0, 3.0) for w in range(1, 41) for _ in range(1)]
        # a week-41 game with a huge residual must not change the parameters used to price week 41
        a = wf.walk(base + [game(2022, 41, 3, 0.0, 3.0)], "NCAAF")
        b = wf.walk(base + [game(2022, 41, 90, 0.0, 3.0)], "NCAAF")
        pa = [p for g, p, _ in a if g["week"] == 41][0]
        pb = [p for g, p, _ in b if g["week"] == 41][0]
        self.assertEqual(pa, pb)

    def test_prior_used_until_min_fit(self):
        rows = wf.walk([game(2022, 1, 7, 0.0, 3.0), game(2022, 2, 7, 0.0, 3.0)], "NCAAF")
        for _, p, _ in rows:
            self.assertEqual(p["C2"][1], wf.DOC_SIGMA["NCAAF"])
            self.assertEqual(p["C4"][0], 0.5)

    def test_pushes_and_zero_edges_dropped(self):
        rows = wf.walk([game(2022, 1, 3, 3.0, 5.0), game(2022, 1, 7, 2.0, 2.0)], "NCAAF")
        self.assertEqual(rows, [])

    def test_bootstrap_sign(self):
        rows = wf.walk([game(2022, w, 10, 0.0, 3.0) for w in range(1, 40)], "NCAAF")
        d = wf.boot_delta(rows, "C0", "C4")
        self.assertLess(d["delta"], 0)  # model side always covers, so C0 beats the coin flip


if __name__ == "__main__":
    unittest.main()
