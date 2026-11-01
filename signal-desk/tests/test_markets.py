import datetime as dt
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import markets as mk  # noqa: E402

P = mk.load_params("NFL", None, "/nonexistent.json")


def game(**kw):
    f = {"_id": "recG1", "League": "NFL", "Home Team": "Buffalo Bills", "Away Team": "Baltimore Ravens", "Game": "Baltimore Ravens @ Buffalo Bills",
         "Home FPI": 5.0, "Away FPI": 3.0, "HFA": 2.0, "Date": "2026-11-01", "ESPN Event ID": "1"}
    f.update(kw)
    return f


class Prices(unittest.TestCase):
    def test_breakeven(self):
        self.assertAlmostEqual(mk.be_prob(-110), 110 / 210, 4)
        self.assertAlmostEqual(mk.be_prob(150), 0.4, 4)
        self.assertEqual(mk.american_from_prob(0.5238), -110)

    def test_devig(self):
        self.assertAlmostEqual(mk.fair_prob_from_prices(-110, -110), 0.5, 4)


class Grading(unittest.TestCase):
    def test_spread_sides(self):
        self.assertEqual(mk.grade_leg("spread", "home", -3.5, 24, 20), "Win" if 4 - 3.5 > 0 else "Loss")
        self.assertEqual(mk.grade_leg("spread", "away", 3.5, 24, 20), "Loss" if -4 + 3.5 < 0 else "Win")
        self.assertEqual(mk.grade_leg("spread", "home", -4, 24, 20), "Push")

    def test_total(self):
        self.assertEqual(mk.grade_leg("total", "over", 43.5, 24, 20), "Win")
        self.assertEqual(mk.grade_leg("total", "under", 44, 24, 20), "Push")
        self.assertEqual(mk.grade_leg("total", "under", 40.5, 24, 20), "Loss")

    def test_moneyline(self):
        self.assertEqual(mk.grade_leg("moneyline", "away", 0, 20, 24), "Win")
        self.assertEqual(mk.grade_leg("moneyline", "home", 0, 20, 24), "Loss")
        self.assertEqual(mk.grade_leg("moneyline", "home", 0, 20, 20), "Push")

    def test_teaser_leg_uses_teased_line(self):
        # away +3.5 teased to +9.5 loses by 8 -> wins
        self.assertEqual(mk.grade_leg("teaser_leg", "away", 9.5, 28, 20, "spread"), "Win")
        self.assertEqual(mk.grade_leg("teaser_leg", "over", 37.5, 20, 20, "total"), "Win")

    def test_combo(self):
        self.assertEqual(mk.grade_combo(["Win", "Win"]), "Win")
        self.assertEqual(mk.grade_combo(["Win", "Loss"]), "Loss")
        self.assertEqual(mk.grade_combo(["Win", "Push"]), "Win")
        self.assertEqual(mk.grade_combo(["Push", "Push"]), "Push")
        self.assertEqual(mk.grade_combo(["Win", "pending"]), "pending")

    def test_units_and_clv(self):
        self.assertAlmostEqual(mk.units_won("Win", 1, -110), 0.909, 3)
        self.assertEqual(mk.units_won("Loss", 0.5, -110), -0.5)
        self.assertEqual(mk.clv_points("spread", "home", -3, -4), 1)
        self.assertEqual(mk.clv_points("total", "over", 44, 45.5), 1.5)
        self.assertEqual(mk.clv_points("total", "under", 44, 45.5), -1.5)


class Teasers(unittest.TestCase):
    def test_key_numbers_raise_cover_probability(self):
        plain = mk.cover(0, -1.5 + 6, 13.5, "NFL")[0]
        smooth = 1 - mk.ND.cdf((-(4.5)) / 13.5)
        self.assertGreater(plain, 0.5)
        self.assertAlmostEqual(sum(mk.margin_distribution(2, 13.5, "NFL").values()), 1, 6)
        self.assertTrue(abs(plain - smooth) < 0.05)

    def test_crossing(self):
        self.assertTrue(mk._crosses(-7.5, -1.5, 7))
        self.assertTrue(mk._crosses(-7.5, -1.5, 3))
        self.assertFalse(mk._crosses(-1.5, 4.5, 7))
        self.assertTrue(mk._crosses(1.5, 7.5, 7))

    def test_leg_stores_base_and_teased(self):
        f = game()
        proj = mk.project_game(f, {"home_margin_line": 3.5, "total": 45.5}, P)
        leg = mk.teaser_leg(f, proj, "spread", P)
        self.assertEqual(leg["line"] - leg["base_line"], 6.0)
        tl = mk.teaser_leg(f, proj, "total", P, over=True)
        self.assertEqual(tl["line"], 39.5)
        self.assertEqual(tl["base_line"], 45.5)

    def test_payout_break_even(self):
        legs = [{"game_id": "a", "market_kind": "spread", "side": "home", "prob": 0.8, "price": None},
                {"game_id": "b", "market_kind": "spread", "side": "home", "prob": 0.8, "price": None}]
        c = mk.combo(legs, "teaser", P)
        self.assertAlmostEqual(c["prob"], 0.64, 3)
        self.assertAlmostEqual(c["break_even_prob"], mk.be_prob(-120), 3)
        self.assertGreater(c["edge"], 0.08)


class Parlays(unittest.TestCase):
    def test_independent_legs_multiply(self):
        legs = [{"game_id": "a", "market_kind": "spread", "side": "home", "prob": 0.6, "price": -110},
                {"game_id": "b", "market_kind": "total", "side": "over", "prob": 0.55, "price": -110}]
        c = mk.combo(legs, "parlay", P)
        self.assertAlmostEqual(c["prob"], 0.33, 3)
        self.assertAlmostEqual(c["break_even_prob"], 0.2744, 3)
        self.assertEqual(c["same_game"], False)

    def test_same_game_spread_and_ml_are_correlated(self):
        legs = [{"game_id": "a", "market_kind": "spread", "side": "home", "prob": 0.6, "price": -110},
                {"game_id": "a", "market_kind": "moneyline", "side": "home", "prob": 0.7, "price": -200}]
        jp = mk.joint_prob(legs)
        self.assertGreater(jp, 0.6 * 0.7 + 0.05)
        self.assertLessEqual(jp, 0.6 + 0.01)

    def test_combo_builder_skips_duplicate_game_margin_legs(self):
        base = {"tier": "Lean", "units": 0.5, "price": -110.0, "game": "g"}
        singles = [{**base, "game_id": "a", "market": "spread", "side": "home", "prob": 0.58, "selection": "A -3"},
                   {**base, "game_id": "a", "market": "moneyline", "side": "home", "prob": 0.7, "selection": "A ML"},
                   {**base, "game_id": "b", "market": "total", "side": "over", "prob": 0.57, "selection": "Over 45"}]
        out = mk.build_combos(singles, [], P)
        for c in out["parlay"]:
            kinds = [l["market_kind"] for l in c["legs"] if l["game_id"] == "a"]
            self.assertLessEqual(len(kinds), 1)


class Projections(unittest.TestCase):
    def test_total_uses_scoring_detail(self):
        f = game(**{"Scoring Detail": json.dumps({"home": {"pf": 30, "pa": 24, "n": 8}, "away": {"pf": 28, "pa": 22, "n": 8}})})
        proj = mk.project_game(f, {"home_margin_line": 3.5, "total": 45.5}, P)
        self.assertGreater(proj["proj_total"], 45.5)
        pk = mk.total_pick(f, proj, None, P)
        self.assertEqual(pk["side"], "over")

    def test_weather_and_qb_lower_total_only_when_live(self):
        f = game(**{"Weather Note": "wind 25 mph | sev=1.0", "QB Starter Note": "HOME QB OUT (x)"})
        shadow = mk.project_game(f, {"home_margin_line": 3.5, "total": 45.5}, P, factor_live=False)
        live = mk.project_game(f, {"home_margin_line": 3.5, "total": 45.5}, P, factor_live=True)
        self.assertEqual(shadow["proj_total"], 45.5)
        self.assertLess(live["proj_total"], 45.5)
        self.assertEqual(shadow["proj_total_shadow"], live["proj_total"])

    def test_moneyline_prefers_edge_and_estimates_missing_price(self):
        f = game()
        proj = mk.project_game(f, {"home_margin_line": 3.5, "total": 45.5}, P)
        pk = mk.moneyline_pick(f, proj, {"ml_home": -170, "ml_away": 145}, P)
        self.assertIn(pk["side"], ("home", "away"))
        self.assertFalse(pk["price_estimated"])
        self.assertTrue(mk.moneyline_pick(f, proj, None, P)["price_estimated"])

    def test_every_game_gets_every_market_even_no_play(self):
        f = game()
        proj = mk.project_game(f, {"home_margin_line": 3.5, "total": 45.5}, P)
        self.assertEqual(mk.moneyline_pick(f, proj, None, P)["market"], "moneyline")
        self.assertEqual(mk.total_pick(f, proj, None, P)["tier"], "No Play")


class Odds(unittest.TestCase):
    def test_parse_and_live_flag(self):
        item = {"provider": {"name": "Draft Kings"}, "spread": -3.5, "overUnder": 45.5,
                "homeTeamOdds": {"favorite": True, "moneyLine": -180, "spreadOdds": -110, "open": {"pointSpread": {"american": "-2.5"}}},
                "awayTeamOdds": {"favorite": False, "moneyLine": 150, "spreadOdds": -110}}
        live = {"provider": {"name": "DraftKings - Live Odds"}, "spread": -1}
        o = mk.parse_odds({"items": [item, live]})
        self.assertEqual(o["home_margin_line"], 3.5)
        self.assertTrue(o["in_progress"])
        self.assertEqual(o["open_margin_line"], 2.5)
        self.assertEqual(o["ml_away"], 150)

    def test_line_log_appends_only_on_change(self):
        rows = []
        n = {"record_id": "r", "home_margin_line": 3.5, "total": 45.5, "ts": "t1"}
        rows = mk.log_lines(rows, [dict(n)])
        rows = mk.log_lines(rows, [dict(n, ts="t2")])
        self.assertEqual(len(rows), 1)
        rows = mk.log_lines(rows, [dict(n, home_margin_line=4.5, ts="t3")])
        self.assertEqual(len(rows), 2)


class Cycle(unittest.TestCase):
    def test_run_freeze_and_grade(self):
        today = dt.date(2026, 11, 1)
        f = game(**{"Scoring Detail": json.dumps({"home": {"pf": 30, "pa": 24, "n": 8}, "away": {"pf": 28, "pa": 22, "n": 8}})})
        odds = {"provider": "DK", "in_progress": False, "home_margin_line": 3.5, "total": 45.5, "ml_home": -170, "ml_away": 145}
        picks = {}
        doc = mk.run([f], {}, today, lambda _f: odds, [], picks, False, "t1")
        markets = {r["market"] for r in picks.values()}
        self.assertTrue({"total", "moneyline", "teaser_leg"} <= markets)
        self.assertEqual(len(doc["games"]), 1)
        # game finishes: freeze and grade
        f["Home Score"], f["Away Score"] = 31, 20
        mk.freeze_started([f], picks, [])
        n = mk.grade_picks([f], picks, mk.log_lines([], doc.pop("new_lines")), "t2")
        self.assertGreaterEqual(n, 2)
        self.assertEqual(picks["total:recG1"]["result"], "Loss" if picks["total:recG1"]["side"] == "under" else "Win")
        # frozen picks are not rewritten
        before = dict(picks["total:recG1"])
        mk.run([dict(f, **{"Home Score": None})], {}, today, lambda _f: dict(odds, total=50), [], picks, False, "t3")
        self.assertEqual(picks["total:recG1"]["line"], before["line"])


if __name__ == "__main__":
    unittest.main()


class Learning(unittest.TestCase):
    def rows(self, n, market="total", league="NFL", win_rate=0.5, prob=0.7):
        out = []
        for i in range(n):
            out.append({"market": market, "league": league, "result": "Win" if i < int(n * win_rate) else "Loss", "prob": prob, "edge": 1, "edge_unit": "pts",
                        "tier": "Lean", "units": 0.45, "stake": 0.5, "clv": 0.5, "factors": "weather: wind" if i % 2 else ""})
        return out

    def test_small_samples_never_tune(self):
        import market_learning as ml
        new, events, notes = ml.tune(self.rows(12), {}, "2026-11-01")
        self.assertEqual(events, [])
        self.assertEqual(new, {})
        self.assertIn("need 30", notes[0])

    def test_overconfident_market_gets_shrunk_with_logged_evidence(self):
        import market_learning as ml
        new, events, _ = ml.tune(self.rows(40, win_rate=0.5, prob=0.75), {}, "2026-11-01")
        self.assertEqual(len(events), 1)
        e = events[0]
        self.assertEqual((e["league"], e["market"], e["setting"]), ("NFL", "total", "probability shrink"))
        self.assertEqual(e["sample_size"], 40)
        self.assertLess(new["NFL"]["shrink"]["total"], 1.0)
        self.assertGreaterEqual(new["NFL"]["shrink"]["total"], 1.0 - ml.MAX_STEP - 1e-9)

    def test_calibrated_market_unchanged(self):
        import market_learning as ml
        new, events, _ = ml.tune(self.rows(40, win_rate=0.7, prob=0.7), {}, "2026-11-01")
        self.assertEqual(events, [])

    def test_scorecard_fields(self):
        import market_learning as ml
        sc = ml.scorecard(self.rows(40, win_rate=0.6))
        self.assertEqual(sc["n"], 40)
        self.assertEqual(sc["win_rate"], 0.6)
        self.assertIn("weather", sc["factors"])
        self.assertAlmostEqual(sc["units"], 18.0, 1)

    def test_parlay_legs_are_flattened(self):
        import market_learning as ml
        legs = [{"result": "Win", "prob": 0.6}, {"result": "Loss", "prob": 0.55}]
        rows = ml.outcome_rows([{"market": "parlay", "league": "NFL", "result": "Loss", "prob": "0.3", "legs_json": json.dumps(legs), "factors": ""}])
        self.assertEqual(sorted(r["market"] for r in rows), ["parlay", "parlay_leg", "parlay_leg"])

    def test_event_log_roundtrip(self):
        import tempfile, learning_events as le
        p = os.path.join(tempfile.mkdtemp(), "learning_log.csv")
        le.append([le.event("NFL", "total", "k", 0.3, 0.2, "ev", 31, "t", "2026-11-01")], p)
        self.assertEqual(le.read(p)[0]["sample_size"], "31")
        self.assertFalse(le.moved(0.30, 0.305))


class OpsFixTests(unittest.TestCase):
    def test_ensure_header_creates_log(self):
        import tempfile
        import learning_events as le
        p = os.path.join(tempfile.mkdtemp(), "learning_log.csv")
        le.ensure_header(p)
        self.assertTrue(open(p).read().startswith("date,league,market"))

    def test_parse_log_reads_bim_summary_lines(self):
        import ops_export
        info = ops_export.parse_log("Mode: LIVE\nRows updated: 2\n")
        self.assertEqual(info["mode"], "LIVE")
        self.assertEqual(info["rows_updated"], 2)
