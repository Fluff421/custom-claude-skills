import base64
import datetime as dt
import gzip
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import splash_lines as sl  # noqa: E402
import splash_pricecheck as spc  # noqa: E402

NOW = dt.datetime(2026, 11, 4, 23, 0, tzinfo=dt.timezone.utc)
GAMES = [
    {"_id": "r1", "Game": "Kentucky @ Tennessee", "Date": "2026-11-07", "League": "NCAAF", "Home Team": "Tennessee", "Away Team": "Kentucky",
     "Vegas Implied Home Margin": 6.5, "Over/Under Line": 51.5},
    {"_id": "r2", "Game": "Western Kentucky @ Middle Tennessee", "Date": "2026-11-07", "League": "NCAAF", "Home Team": "Middle Tennessee",
     "Away Team": "Western Kentucky", "Vegas Implied Home Margin": -1.5, "Over/Under Line": 52.5},
    {"_id": "r3", "Game": "Cleveland Browns @ New Orleans Saints", "Date": "2026-11-08", "League": "NFL", "Home Team": "New Orleans Saints",
     "Away Team": "Cleveland Browns", "Vegas Implied Home Margin": 2.5, "Over/Under Line": 42.5, "Injury Notes": "none"},
    {"_id": "r4", "Game": "Ohio @ Akron", "Date": "2026-11-03", "League": "NCAAF", "Home Team": "Akron", "Away Team": "Ohio",
     "Vegas Implied Home Margin": -12.5, "Over/Under Line": 50.5, "Home Score": 20, "Away Score": 34},
]


def game(lg, away, home, hs, tot, ko, aml=None, hml=None):
    return {"source": "Splash Sports Lines", "date_code": "X", "league": lg, "away_team": away, "home_team": home, "home_away_certain": True,
            "kickoff_central": ko, "away_spread": -hs, "home_spread": hs, "total": tot, "away_ml": aml, "home_ml": hml}


def dump(code, ts, games, counts=None):
    c = {}
    for g in games:
        c[g["league"]] = c.get(g["league"], 0) + 1
    return {"schema": sl.SCHEMA, "source": sl.SOURCE, "date_code": code, "extracted_at_utc": ts, "extracted_at_central": ts,
            "game_count": counts or c, "games": games}


D1 = dump("A", "2026-11-02T02:13:00Z", [game("NCAAF", "Kentucky", "Tennessee", -6.5, 51.5, "2026-11-07 17:15"),
                                         game("NCAAF", "Western Kentucky", "Middle Tennessee", 1.5, 52.5, "2026-11-07 14:30"),
                                         game("NFL", "Browns", "Saints", -2.5, 42.5, "2026-11-08 12:00"),
                                         game("NCAAF", "Ohio", "Akron", 12.5, 50.5, "2026-11-03 18:00")])
D2 = dump("B", "2026-11-04T22:32:00Z", [game("NCAAF", "Kentucky", "Tennessee", -6.5, 50.5, "2026-11-07 17:15"),
                                         game("NCAAF", "Western Kentucky", "Middle Tennessee", 1.5, 53.5, "2026-11-07 14:30"),
                                         game("NFL", "Browns", "Saints", -3.0, 43.5, "2026-11-08 12:00", 126, -148)])


class Load(unittest.TestCase):
    def test_fenced_and_gzip(self):
        raw = json.dumps(D1)
        self.assertEqual(sl.load_dump("text\n```json\n" + raw + "\n```\nNFL 1").get("date_code"), "A")
        gz = "gz:" + base64.b64encode(gzip.compress(raw.encode())).decode()
        self.assertEqual(sl.load_dump(gz)["date_code"], "A")


class Match(unittest.TestCase):
    def test_exact_names_no_suffix_confusion(self):
        f, o, c = sl.match_game(game("NCAAF", "Kentucky", "Tennessee", -6.5, 51.5, "2026-11-07 17:15"), GAMES)
        self.assertEqual((f["_id"], o, len(c)), ("r1", "same", 1))

    def test_nfl_nickname(self):
        f, o, _ = sl.match_game(game("NFL", "Browns", "Saints", -3, 43.5, "2026-11-08 12:00"), GAMES)
        self.assertEqual((f["_id"], o), ("r3", "same"))

    def test_reversed_orientation(self):
        f, o, _ = sl.match_game(game("NFL", "Saints", "Browns", 3, 43.5, "2026-11-08 12:00"), GAMES)
        self.assertEqual((f["_id"], o), ("r3", "reversed"))

    def test_date_window(self):
        f, _, _ = sl.match_game(game("NFL", "Browns", "Saints", -3, 43.5, "2026-11-12 12:00"), GAMES)
        self.assertIsNone(f)

    def test_feed_aliases_match_like_the_validator(self):
        # Seeded Ledger rows use ESPN short names; File 1 keeps Splash names.
        ledger = [{"_id": "m1", "Date": "2026-11-14", "League": "NCAAF", "Home Team": "Miami", "Away Team": "Duke"},
                  {"_id": "m2", "Date": "2026-11-14", "League": "NCAAF", "Home Team": "Marshall", "Away Team": "App State"},
                  {"_id": "m3", "Date": "2026-11-17", "League": "NCAAF", "Home Team": "Kent State", "Away Team": "Miami (OH)"}]
        f, o, _ = sl.match_game(game("NCAAF", "Duke", "Miami (FL)", -13.5, 54.5, "2026-11-14 11:00"), ledger)
        self.assertEqual((f["_id"], o), ("m1", "same"))
        f, o, _ = sl.match_game(game("NCAAF", "Appalachian State", "Marshall", 1.5, 54.5, "2026-11-14 17:00"), ledger)
        self.assertEqual((f["_id"], o), ("m2", "same"))
        f, _, _ = sl.match_game(game("NCAAF", "Miami (FL)", "Kent State", 3, 50, "2026-11-17 18:00"), ledger)
        self.assertIsNone(f)


class Validate(unittest.TestCase):
    def test_good(self):
        errs, notes = sl.validate(D2, GAMES, [], NOW)
        self.assertEqual((errs, notes), ([], []))

    def test_rejects_sign_schema_stale(self):
        bad = json.loads(json.dumps(D2))
        bad["schema"] = "x"
        bad["games"][0]["away_spread"] = 6.0
        errs, _ = sl.validate(bad, GAMES, [], NOW)
        self.assertTrue(any("schema" in e for e in errs) and any("away_spread" in e for e in errs))
        old = dict(D2, extracted_at_utc="2026-11-01T00:00:00Z")
        self.assertTrue(any("hours old" in e for e in sl.validate(old, GAMES, [], NOW)[0]))
        self.assertEqual(sl.validate(old, GAMES, [], NOW, allow_stale=True)[0], [])

    def test_count_gap_explained_by_finished_games(self):
        prev, _, _ = sl.build_rows(D1, GAMES, [], [], {}, "early_import")
        d = dict(D2, game_count={"NCAAF": 3, "NFL": 1})
        errs, notes = sl.validate(d, GAMES, prev, NOW)
        self.assertEqual(errs, [])
        self.assertIn("Ohio @ Akron", notes[0])

    def test_arbitrary_count_error_not_excused_by_finished_game(self):
        prev, _, _ = sl.build_rows(D1, GAMES, [], [], {}, "early_import")
        d = dict(D2, game_count={"NCAAF": 6, "NFL": 1})
        self.assertTrue(sl.validate(d, GAMES, prev, NOW)[0])

    def test_extra_entries_not_excused_by_finished_game(self):
        prev, _, _ = sl.build_rows(D1, GAMES, [], [], {}, "early_import")
        d = dict(D2, game_count={"NCAAF": 1, "NFL": 1})
        self.assertTrue(sl.validate(d, GAMES, prev, NOW)[0])

    def test_count_gap_unexplained(self):
        d = dict(D2, game_count={"NCAAF": 6, "NFL": 1})
        errs, _ = sl.validate(d, GAMES, [], NOW)
        self.assertTrue(errs)


class Rows(unittest.TestCase):
    def setUp(self):
        self.r1, _, _ = sl.build_rows(D1, GAMES, [], [], {}, "early_import")
        market = [{"ts": "2026-11-02T01:00:00+00:00", "record_id": "r3", "home_margin_line": "2.5", "total": "42.5"},
                  {"ts": "2026-11-04T20:00:00+00:00", "record_id": "r3", "home_margin_line": "3.0", "total": "42.5"}]
        self.r2, self.un, self.fl = sl.build_rows(D2, GAMES, self.r1, market, {})

    def test_early_and_movement(self):
        self.assertTrue(all(r["snapshot_kind"] == "early_import" and r["movement_seq"] == 0 for r in self.r1))
        s = {r["record_id"]: r for r in self.r2}
        self.assertEqual(s["r3"]["snapshot_kind"], "movement")
        self.assertEqual(s["r3"]["movement_seq"], 1)
        self.assertEqual((s["r3"]["home_margin"], s["r3"]["d_margin_prev"], s["r3"]["d_margin_early"]), (3.0, 0.5, 0.5))
        self.assertEqual(s["r3"]["moved_toward"], "New Orleans Saints")
        self.assertIn("followed the sportsbook", s["r3"]["move_hint"])
        self.assertIn("3", s["r3"]["key_numbers_crossed"])
        self.assertEqual(s["r1"]["d_total_prev"], -1.0)
        self.assertEqual(s["r2"]["home_margin"], -1.5)   # Splash home +1.5 -> ledger margin -1.5

    def test_crossed(self):
        self.assertEqual(sl.crossed(2.5, 3.0, sl.NFL_KEYS), ["3"])
        self.assertEqual(sl.crossed(6.5, 7.5, sl.NFL_KEYS), ["7"])
        self.assertIn("favorite flipped", sl.crossed(1.5, -1.5, sl.NFL_KEYS))
        self.assertEqual(sl.crossed(4.5, 5.5, sl.NFL_KEYS), [])

    def test_learning(self):
        rows = self.r1 + [dict(self.r1[3], snapshot_kind="movement", captured_at_utc="2026-11-03T19:18:00Z", d_margin_early=-1.0)]
        out = sl.movement_learning(rows, {f["_id"]: f for f in GAMES})
        self.assertEqual(out[0][:3], ["NCAAF", 1, 1])   # moved toward Ohio; Ohio won by 14 > 12.5


class PriceCheck(unittest.TestCase):
    def test_check_game_uses_current_line(self):
        seen = []

        def pricer(f, market, side, line, price):
            seen.append((market, side, line, price))
            if market == "spread":
                return {"side": "home", "tier": "Lean" if line == -3.0 else "Strong Play", "prob": 0.56, "edge": 1.2, "proj": 4.2}
            if market == "total":
                return {"side": "over", "tier": "No Play", "prob": 0.52, "edge": 0.4, "proj": line + 0.4}
            return {"side": "home", "tier": "No Play", "prob": 0.6, "edge": 0.01 if side == "home" else -0.05, "proj": 4.2}
        snap = {"home_margin": "3.0", "total": "43.5", "away_ml": "126", "home_ml": "-148", "snapshot_id": "B"}
        sc_tp = spc.sc.teaser_leg_prob
        spc.sc.teaser_leg_prob = lambda *a, **k: 0.7
        try:
            r = spc.check_game(GAMES[2], snap, pricer, {}, False)
        finally:
            spc.sc.teaser_leg_prob = sc_tp
        self.assertIn(("spread", "home", -3.0, None), seen)
        self.assertIn(("spread", "home", -2.5, None), seen)   # early import comparison
        self.assertEqual(r["spread"]["pick"], "New Orleans Saints -3")
        self.assertEqual((r["spread"]["tier"], r["spread"]["import_tier"]), ("Lean", "Strong Play"))
        self.assertEqual(r["moneyline"]["pick"], "New Orleans Saints ML -148")
        self.assertEqual(r["spread"]["teaser_leg"]["pick"], "New Orleans Saints +3 (teased)")


if __name__ == "__main__":
    unittest.main()
