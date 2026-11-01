import datetime as dt
import json
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import factor_learning as fl  # noqa: E402
import factors as fx  # noqa: E402
import qb_nfl  # noqa: E402
import situational as sit  # noqa: E402
import weather as wx  # noqa: E402

norm = lambda s: s.lower().replace(" ", "").replace(".", "")  # noqa: E731


class Weather(unittest.TestCase):
    def test_severity(self):
        self.assertEqual(wx.severity(5, 10, 0, 60), 0.0)
        self.assertEqual(wx.severity(22, 0, 0, 60), 1.0)
        self.assertEqual(wx.severity(16, 0, 0, 60), 0.6)
        self.assertEqual(wx.severity(0, 0, 0.5, 30), 0.7)
        self.assertEqual(wx.severity(0, 70, 0, 60), 0.4)

    def test_pick_hours_uses_kickoff_window(self):
        h = {"time": [f"2026-11-02T{i:02d}:00" for i in range(24)], "temperature_2m": list(range(24)),
             "wind_speed_10m": [5] * 18 + [30] * 6, "precipitation_probability": [0] * 24, "snowfall": [0] * 24}
        k = dt.datetime(2026, 11, 2, 17, 30, tzinfo=dt.timezone.utc)
        w = wx.pick_hours(h, k, 3)  # hours 17, 18, 19
        self.assertEqual(w["wind"], 30)
        self.assertEqual(w["temp"], 17)

    def test_note_roundtrip_and_indoor(self):
        n = wx.note({"temp": 28, "wind": 18, "precip": 20, "snow": 0}, False)
        self.assertAlmostEqual(wx.sev_from_note(n), 0.6)
        self.assertEqual(wx.sev_from_note(wx.note(None, True)), 0.0)
        self.assertIsNone(wx.sev_from_note("68F, Mostly sunny | no severity"))

    def test_points_shrink_margin_toward_zero_and_cap(self):
        self.assertLess(wx.weather_points(10, 1.0), 0)   # home favoured: bad weather lowers home margin
        self.assertGreater(wx.weather_points(-10, 1.0), 0)
        self.assertEqual(wx.weather_points(10, 0), 0.0)
        self.assertGreaterEqual(wx.weather_points(40, 1.0), -wx.MAX_WEATHER_PTS)

    def test_forecast_note_never_raises_and_skips_far_games(self):
        now = dt.datetime(2026, 11, 1, 12, tzinfo=dt.timezone.utc)
        def boom(u):
            raise RuntimeError("x")
        self.assertEqual(wx.forecast_note("Buffalo", "NY", now + dt.timedelta(days=2), now, False, boom, {}, {}), "")
        self.assertEqual(wx.forecast_note("Buffalo", "NY", now + dt.timedelta(days=20), now, False, boom, {}, {}), "")
        self.assertIn("indoor", wx.forecast_note("Detroit", "MI", now, now, True, boom, {}, {}))

    def test_weather_enters_adjusted_margin(self):
        base = {"Home FPI": 20, "Away FPI": 10, "HFA": 2.5, "Vegas Implied Home Margin": 10, "League": "NFL"}
        a = fx.compute(base, dt.date(2026, 11, 1), "x")
        b = fx.compute({**base, "Weather Note": "20F, wind 25mph | sev=1.00 | open-meteo"}, dt.date(2026, 11, 1), "x")
        self.assertLess(b["adj_model"], a["adj_model"])
        c = fx.compute({**base, "Weather Note": "20F | sev=1.00"}, dt.date(2026, 11, 1), "x", scales={"weather": 0.0})
        self.assertEqual(c["adj_model"], a["adj_model"])  # a learned scale of 0 switches it off


class NflQb(unittest.TestCase):
    DEPTH = {"depthchart": [{"positions": {"qb": {"athletes": [{"displayName": "Starter One"}, {"displayName": "Backup Two"}]}}}]}

    def test_starter_out(self):
        r = qb_nfl.team_row("X", "home", self.DEPTH, ["Starter One (QB) Out", "Some OL (OT) Out"], norm, "2026-11-01")
        self.assertEqual(r["classification"], "starter_out")
        self.assertEqual(r["replacement"], "Backup Two")

    def test_backup_listed_is_not_starter_out(self):
        r = qb_nfl.team_row("X", "home", self.DEPTH, ["Backup Two (QB) Out"], norm, "2026-11-01")
        self.assertEqual(r["classification"], "starter_playing")
        note = sit.qb_note([r], "X", "Y", norm)
        self.assertEqual(sit.qb_fractions(note), {"home": 0.0})

    def test_questionable_and_clean(self):
        self.assertEqual(qb_nfl.classify(["A"], ["A (QB) Questionable"], norm)[0], "starter_questionable")
        self.assertEqual(qb_nfl.classify(["A"], [], norm)[0], "starter_playing")
        self.assertEqual(qb_nfl.classify([], [], norm)[0], "unknown")

    def test_backup_listing_no_longer_charges_starter_points(self):
        f = {"Home FPI": 10, "Away FPI": 10, "HFA": 2.0, "Vegas Implied Home Margin": 2, "League": "NFL",
             "Injury Notes": "AWAY X: Backup Two (QB) Out | HOME Y: none listed"}
        before = fx.compute(f, dt.date(2026, 11, 1), "x")
        r = qb_nfl.team_row("X", "away", self.DEPTH, ["Backup Two (QB) Out"], norm, "d")
        after = fx.compute({**f, "QB Starter Note": sit.qb_note([r], "Y", "X", norm)}, dt.date(2026, 11, 1), "x")
        self.assertGreater(before["inj_adj"], 0)
        self.assertEqual(after["inj_adj"], 0)


def synth(n, truths, seed=7):
    rnd = random.Random(seed)
    rows = []
    for _ in range(n):
        parts = {"lookahead": rnd.choice([0, 0, 0, 1.0, -1.0]), "rest": rnd.choice([0, 0, 0.6, -0.6, 1.2]),
                 "travel": rnd.choice([0, 0, 0.5, -0.5]), "revenge": rnd.choice([0, 0, 0.3, -0.3]),
                 "weather": rnd.choice([0, 0, -0.5, 0.5])}
        inj = rnd.uniform(-4, 4)
        model = rnd.uniform(-10, 10)
        actual = model + truths["inj"] * inj + sum(truths[k] * v for k, v in parts.items()) + rnd.gauss(0, 12)
        rows.append({"actual": actual, "model": model, "vegas": model, "inj": inj, "parsed": True, "parts": parts,
                     "situ": sum(parts.values())})
    return rows


class PerFactor(unittest.TestCase):
    def test_each_factor_gets_its_own_scale(self):
        truths = {"inj": 1.0, "lookahead": 0.0, "rest": 3.0, "travel": 1.0, "revenge": 0.0, "weather": 1.0}
        out = fl.factor_scales(synth(6000, truths))
        self.assertTrue(out["ok"])
        self.assertEqual(set(out["fitted"]), {"inj", "lookahead", "rest", "travel", "revenge", "weather"})
        self.assertGreater(out["scale_rest"], out["scale_revenge"] + 0.5)   # data separates them
        self.assertLess(out["scale_lookahead"], 0.3)
        self.assertEqual(out["scale_situ"], out["scale_lookahead"])        # legacy alias

    def test_factor_with_too_few_nonzero_games_stays_unfitted(self):
        rows = synth(60, {"inj": 1, "lookahead": 0, "rest": 0, "travel": 0, "revenge": 0, "weather": 0})
        for r in rows:
            r["parts"]["revenge"] = 0.0
        out = fl.factor_scales(rows)
        self.assertTrue(out["ok"])
        self.assertNotIn("scale_revenge", out)

    def test_gates_below_minimum(self):
        self.assertFalse(fl.factor_scales(synth(10, {"inj": 1, "lookahead": 0, "rest": 0, "travel": 0, "revenge": 0, "weather": 0}))["ok"])

    def test_old_detail_records_still_load(self):
        f = {"Home Score": 30, "Away Score": 20, "Home FPI": 5, "Away FPI": 3, "HFA": 2, "Vegas Implied Home Margin": 4, "League": "NFL",
             "Factor Detail": json.dumps({"away_inj_pts": 1, "home_inj_pts": 0, "lookahead": {"home": True}, "situ_points": 0.5, "inj_parsed": True})}
        r = fl.game_rows([f])[0]
        self.assertEqual(r["parts"], {"lookahead": -0.5})


if __name__ == "__main__":
    unittest.main()
