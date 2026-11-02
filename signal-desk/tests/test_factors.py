import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import factors as fx  # noqa: E402

TODAY = dt.date(2026, 11, 1)
ESPN = ("[ESPN 2026-11-01T16:12Z] AWAY: Malik Muhammad II (CB) Questionable; Kyle Monangai (RB) Out | "
        "HOME: Charles Cross (OT) Out; Drew Lock (QB) Questionable; Uchenna Nwosu (LB) Doubtful")
AUTO = ("[Injuries AUTO | SECONDARY, unverified] Covers (latest entry Oct 21) + DraftEdge (updated October 30, 2026 11:56 AM). "
        "C=Covers, D=DraftEdge, dates are Covers entry dates. Blank is not healthy. AWAY Mississippi State: "
        "Kamario Taylor QB OUT (Foot) [both; Covers Q Oct 17]; F. Bothwell RB Q (Foot) [C Oct 17] | "
        "HOME Texas: Trevor Goosby OT OUT (Knee) [both]; Colin Simmons LB Q (Ankle) [D]; +3 more")


class Parse(unittest.TestCase):
    def test_espn(self):
        p = fx.parse_injuries(ESPN, TODAY)
        self.assertTrue(p["parsed"])
        self.assertEqual([(e["pos"], e["status"]) for e in p["away"]], [("DB", "questionable"), ("RB", "out")])
        self.assertEqual([(e["pos"], e["status"]) for e in p["home"]], [("OL", "out"), ("QB", "questionable"), ("LB", "doubtful")])

    def test_auto_note_and_stale(self):
        p = fx.parse_injuries(AUTO, TODAY)
        self.assertEqual([e["pos"] for e in p["away"]], ["QB", "RB"])
        self.assertFalse(p["away"][0]["stale"])  # DraftEdge-confirmed
        self.assertTrue(p["away"][1]["stale"])   # Covers-only, Oct 17 is 15 days old
        self.assertEqual(len(p["home"]), 2)      # "+3 more" is not a player

    def test_blank_is_not_healthy(self):
        self.assertFalse(fx.parse_injuries("", TODAY)["parsed"])
        self.assertFalse(fx.parse_injuries(None, TODAY)["parsed"])
        self.assertFalse(fx.parse_injuries("garbage", TODAY)["parsed"])


class Points(unittest.TestCase):
    def test_qb_out_beats_depth(self):
        qb, _ = fx.team_points([{"pos": "QB", "weight": 1.0, "stale": False}], "NFL")
        ol, _ = fx.team_points([{"pos": "OL", "weight": 1.0, "stale": False}], "NFL")
        self.assertGreater(qb, ol * 3)

    def test_cap(self):
        many = [{"pos": "QB", "weight": 1.0, "stale": False}] * 10
        self.assertEqual(fx.team_points(many, "NFL")[0], fx.TEAM_CAP["NFL"])


class Compute(unittest.TestCase):
    def row(self, **kw):
        base = {"League": "NFL", "Home FPI": 4.3, "Away FPI": 3.8, "HFA": 2.0, "Vegas Implied Home Margin": 3.0, "Injury Notes": ESPN}
        base.update(kw)
        return base

    def test_sign_and_edge(self):
        r = fx.compute(self.row(), TODAY, "t")
        # home has OL out + QB questionable + LB doubtful; away has RB out + CB questionable: home hurt more
        self.assertLess(r["inj_adj"], 0)
        self.assertAlmostEqual(r["adj_edge"], round(r["adj_model"] - 3.0, 1), places=1)

    def test_missing_inputs(self):
        self.assertIsNone(fx.compute({"League": "NFL"}, TODAY, "t"))
        self.assertIsNone(fx.compute(self.row(**{"Home FPI": None}), TODAY, "t"))

    def test_lookahead_hurts_flagged_team(self):
        r = fx.compute(self.row(**{"Injury Notes": "", "Look-Ahead Note": "Home side may look ahead to X (next-opp FPI +9 vs today)."}), TODAY, "t")
        self.assertEqual(r["situ_adj"], -0.5)
        self.assertFalse(r["detail"]["inj_parsed"])

    def test_scales_apply(self):
        a = fx.compute(self.row(), TODAY, "t", scale_inj=1.0)["inj_adj"]
        b = fx.compute(self.row(), TODAY, "t", scale_inj=0.0)["inj_adj"]
        self.assertEqual(b, 0.0)
        self.assertNotEqual(a, 0.0)


if __name__ == "__main__":
    unittest.main()


class UnverifiedQB(unittest.TestCase):
    TODAY = __import__("datetime").date(2026, 11, 2)
    BASE = {"League": "NFL", "Home FPI": 0.0, "Away FPI": 0.0, "HFA": 2.0, "Vegas Implied Home Margin": 2.0}

    def run_(self, note, qb_note=None):
        import factors as fx
        return fx.compute({**self.BASE, "Injury Notes": note, "QB Starter Note": qb_note}, self.TODAY, "now")["detail"]

    def test_two_backups_count_once_at_backup_value(self):
        d = self.run_("AWAY: A One (QB) Out; B Two (QB) Out | HOME: none listed")
        self.assertAlmostEqual(d["away_inj_pts"], 0.5)
        self.assertEqual(d["away_by_pos"], {"QB": 0.5})
        self.assertIn("away", d["qb_unverified"])

    def test_starter_check_still_gives_full_value(self):
        d = self.run_("AWAY: A One (QB) Out; B Two (QB) Out | HOME: none listed",
                      "AWAY QB OUT A One [auto espn 2026-11-02]")
        self.assertGreaterEqual(d["away_inj_pts"], 3.5)
        self.assertEqual(d["qb_unverified"], {})

    def test_backup_listed_starter_playing_is_zero(self):
        d = self.run_("AWAY: B Two (QB) Out | HOME: none listed", "AWAY QB PLAYING A One [auto espn 2026-11-02]")
        self.assertEqual(d["away_inj_pts"], 0.0)


class UnverifiedQBCap(unittest.TestCase):
    def test_pick_capped_at_lean_without_starter_check(self):
        import picks
        old = picks.FACTOR_MODE
        picks.FACTOR_MODE = "live"
        try:
            p = {"sigma": 12.5, "lean": 1.0, "strong": 2.5, "max": 4.0,
                 "units": {"Lean": 0.5, "Strong Play": 1.5, "Max Play": 3.0}, "multipliers": {}}
            f = {"League": "NFL", "Home Team": "H", "Away Team": "A", "Home FPI": 8.0, "Away FPI": 0.0, "HFA": 2.0,
                 "Vegas Implied Home Margin": 0.0, "Injury Notes": "AWAY: B Two (QB) Out | HOME: none listed"}
            new, edge, tier, prob, units = picks.evaluate(f, p, {}, "now")
            self.assertEqual(tier, "Lean")
            self.assertIn("QB unverified (away B Two): Max Play capped at Lean", new["Sharp-Sheet Data Completeness"])
            new, edge, tier, prob, units = picks.evaluate({**f, "QB Starter Note": "AWAY QB PLAYING A One [auto espn 2026-11-02]"},
                                                          p, {}, "now")
            self.assertEqual(tier, "Max Play")
        finally:
            picks.FACTOR_MODE = old
