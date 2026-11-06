"""Probability save rule: re-price pending auto picks on side, tier, a 0.5-point win-prob move or a units change,
and on game day only until kickoff."""
import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import picks  # noqa: E402

SAVED = {"Recommended Side": "Arizona Cardinals +10.5", "Sharp-Sheet Tier": "Lean",
         "Sharp-Sheet Est. Win Prob %": 0.7657, "Sharp-Sheet Suggested Units": 0.5}


def new(prob=0.7657, units=0.5, side="Arizona Cardinals +10.5"):
    return {"Recommended Side": side, "Sharp-Sheet Est. Win Prob %": prob, "Sharp-Sheet Suggested Units": units}


class Reasons(unittest.TestCase):
    def test_sigma_and_feature_changes_refresh_even_below_probability_threshold(self):
        f = {"League": "NFL", "Home Team": "Dallas Cowboys", "Away Team": "Arizona Cardinals",
             "Home FPI": 1, "Away FPI": 0, "Vegas Implied Home Margin": 3}
        p = {**picks.DEFAULTS, "sigma": 12.5}
        saved = picks.evaluate(f, p, {}, "2026-11-06 14:00Z")[0]
        for fields, params in ((f, {**p, "sigma": 12.51}), ({**f, "Weather Note": "new forecast"}, p)):
            candidate = picks.evaluate(fields, params, {}, "2026-11-06 15:00Z")[0]
            self.assertIn("features", picks.reprice_reasons(saved, candidate, saved["Sharp-Sheet Tier"]))
        candidate = picks.evaluate({**f, "ESPN Pulled At": "2026-11-06T15:00Z"}, p, {}, "2026-11-06 15:00Z")[0]
        self.assertEqual(picks.reprice_reasons(saved, candidate, saved["Sharp-Sheet Tier"]), [])

    def test_no_change_keeps_saved_pick(self):
        self.assertEqual(picks.reprice_reasons(SAVED, new(0.7680), "Lean"), [])  # 0.23 pts: under the drift

    def test_prob_drift_at_half_point(self):
        self.assertEqual(picks.reprice_reasons(SAVED, new(0.7707), "Lean"), ["prob"])
        self.assertEqual(picks.reprice_reasons(SAVED, new(0.7607), "Lean"), ["prob"])

    def test_units_side_tier_and_withdraw(self):
        self.assertEqual(picks.reprice_reasons(SAVED, new(units=1.0), "Lean"), ["units"])
        self.assertEqual(picks.reprice_reasons(SAVED, new(side="Dallas Cowboys -10.5"), "Lean"), ["side"])
        self.assertEqual(picks.reprice_reasons(SAVED, new(), "Strong Play"), ["tier"])
        self.assertEqual(picks.reprice_reasons(SAVED, None, None), ["below Lean"])

    def test_missing_saved_prob_reprices(self):
        self.assertIn("prob", picks.reprice_reasons({**SAVED, "Sharp-Sheet Est. Win Prob %": None}, new(), "Lean"))


def event(state, iso):
    return [{"id": "1", "date": iso, "status": {"type": {"state": state}},
             "competitions": [{"competitors": [
                 {"homeAway": "home", "team": {"displayName": "Dallas Cowboys", "abbreviation": "DAL"}},
                 {"homeAway": "away", "team": {"displayName": "Arizona Cardinals", "abbreviation": "ARI"}}]}]}]


class Kickoff(unittest.TestCase):
    F = {"League": "NFL", "Home Team": "Dallas Cowboys", "Away Team": "Arizona Cardinals"}
    NOW = dt.datetime(2026, 11, 8, 17, 0, tzinfo=dt.timezone.utc)

    def test_open_before_kickoff(self):
        ok, note = picks.kickoff_state(self.F, lambda _l: event("pre", "2026-11-08T18:00Z"), self.NOW)
        self.assertTrue(ok, note)

    def test_frozen_at_kickoff_or_live(self):
        self.assertFalse(picks.kickoff_state(self.F, lambda _l: event("pre", "2026-11-08T17:00Z"), self.NOW)[0])
        self.assertFalse(picks.kickoff_state(self.F, lambda _l: event("in", "2026-11-08T18:00Z"), self.NOW)[0])

    def test_unknown_kickoff_is_frozen(self):
        self.assertFalse(picks.kickoff_state(self.F, lambda _l: [], self.NOW)[0])

        def boom(_l):
            raise RuntimeError("403")
        self.assertFalse(picks.kickoff_state(self.F, boom, self.NOW)[0])


if __name__ == "__main__":
    unittest.main()
