import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import splash_compare as sc  # noqa: E402

TODAY = dt.date(2026, 11, 3)
NOW = "2026-11-03 15:00Z"
GAMES = [
    {"_id": "r1", "Game": "Kansas State @ Colorado", "Date": "2026-11-07", "League": "NCAAF", "Home Team": "Colorado", "Away Team": "Kansas State",
     "Vegas Implied Home Margin": 1.5, "Over/Under Line": 55.5},
    {"_id": "r2", "Game": "Auburn @ Ole Miss", "Date": "2026-11-07", "League": "NCAAF", "Home Team": "Ole Miss", "Away Team": "Auburn",
     "Vegas Implied Home Margin": 10.5, "Over/Under Line": 58.5},
    {"_id": "r3", "Game": "Baltimore Ravens @ Buffalo Bills", "Date": "2026-11-01", "League": "NFL", "Home Team": "Buffalo Bills", "Away Team": "Baltimore Ravens",
     "Vegas Implied Home Margin": 3.0, "Over/Under Line": 45.5, "Home Score": 24, "Away Score": 20},
]


def pricer(f, market, side, line, price):
    # stub model: always likes the home team / the over
    if market == "total":
        return {"side": "over", "tier": "Lean", "prob": 0.58, "edge": 2.0, "proj": line + 2}
    return {"side": "home", "tier": "Lean", "prob": 0.6, "edge": 1.5, "proj": 3.0}


class Parse(unittest.TestCase):
    def test_spreads(self):
        t, bad = sc.parse_lines("Alabama -7.5\n- Ole Miss +3 \n3) Kansas State PK\nnonsense here\n\n")
        self.assertEqual([(x["legs"][0]["team"], x["legs"][0]["line"]) for x in t], [("Alabama", -7.5), ("Ole Miss", 3.0), ("Kansas State", 0.0)])
        self.assertEqual(bad, ["nonsense here"])

    def test_totals_both_orders(self):
        t, bad = sc.parse_lines("Baltimore at Buffalo Over 45.5\nUnder 58.5 Auburn @ Ole Miss\nAuburn vs Ole Miss u58")
        self.assertEqual(bad, [])
        self.assertEqual([(x["legs"][0]["side"], x["legs"][0]["line"]) for x in t], [("over", 45.5), ("under", 58.5), ("under", 58.0)])

    def test_moneyline(self):
        t, _ = sc.parse_lines("Buffalo ML -180\nOle Miss moneyline\nAuburn ML +150")
        self.assertEqual([(x["legs"][0]["team"], x["legs"][0]["price"]) for x in t], [("Buffalo", -180.0), ("Ole Miss", None), ("Auburn", 150.0)])

    def test_teaser_and_parlay(self):
        t, bad = sc.parse_lines("Teaser: Alabama -1.5, Over 45.5 Baltimore at Buffalo\nParlay: Alabama -7.5, Buffalo ML -180, Under 50 A at B\nOther: Alabama alt -3.5 at +150")
        self.assertEqual(bad, [])
        self.assertEqual([x["type"] for x in t], ["teaser", "parlay", "other"])
        self.assertEqual(len(t[1]["legs"]), 3)
        self.assertEqual(t[1]["legs"][1]["market"], "moneyline")

    def test_teased_marker(self):
        t, _ = sc.parse_lines("Teaser: Alabama +4.5 teased, Auburn +16.5")
        self.assertTrue(t[0]["legs"][0]["teased"])
        self.assertFalse(t[0]["legs"][1]["teased"])

    def test_single_leg_teaser_is_unreadable(self):
        _, bad = sc.parse_lines("Teaser: Alabama -1.5")
        self.assertEqual(len(bad), 1)


class Compare(unittest.TestCase):
    def run_one(self, text):
        t, _ = sc.parse_lines(text)
        return sc.compare(t, GAMES, NOW, pricer, TODAY, None)

    def test_locked_line_differs_from_import_is_movement_not_error(self):
        rows, un = self.run_one("Ole Miss -11.5")      # ledger early line was -10.5
        r = rows[0]
        self.assertEqual((r["imported_line"], r["locked_line"]), (-10.5, -11.5))
        self.assertEqual(r["movement_for_you"], -1.0)   # line moved against the Ole Miss bettor
        self.assertEqual(un, [])
        self.assertEqual(r["matched"], "yes")

    def test_favorable_move_and_dog(self):
        r = self.run_one("Auburn +11.5")[0][0]
        self.assertEqual(r["imported_line"], 10.5)
        self.assertEqual(r["movement_for_you"], 1.0)

    def test_total_movement_direction(self):
        o = self.run_one("Kansas State at Colorado Over 57")[0][0]
        u = self.run_one("Kansas State at Colorado Under 57")[0][0]
        self.assertEqual(o["imported_line"], 55.5)
        self.assertEqual(o["movement_for_you"], -1.5)
        self.assertEqual(u["movement_for_you"], 1.5)

    def test_started_or_finished_games_are_kept(self):
        rows, un = self.run_one("Baltimore at Buffalo Over 45.5\nBuffalo -3")
        self.assertEqual(len(rows), 2)
        self.assertEqual(un, [])
        self.assertTrue(all(r["status"] == "final" for r in rows))

    def test_unmatched_kept_with_status(self):
        rows, un = self.run_one("Texas -4")
        self.assertEqual(un, ["Texas -4"])
        self.assertEqual(rows[0]["status"], "no matching game")

    def test_model_side_change_between_import_and_lock(self):
        calls = []

        def p(f, market, side, line, price):
            calls.append(line)
            return {"side": "home" if (line or 0) > -11 else "away", "tier": "Lean", "prob": 0.55, "edge": 1}
        t, _ = sc.parse_lines("Ole Miss -11.5")
        r = sc.compare(t, GAMES, NOW, p, TODAY, None)[0][0]
        self.assertEqual(r["model_side_import"], "home")
        self.assertEqual(r["model_side_lock"], "away")
        self.assertEqual(r["side_changed"], "yes")
        self.assertEqual(calls, [-11.5, -10.5])

    def test_teaser_legs_store_base_and_teased(self):
        rows, _ = self.run_one("Teaser: Ole Miss -7.5, Kansas State at Colorado Over 55.5")
        a, b = rows
        self.assertEqual((a["base_line"], a["teased_line"], a["locked_line"]), (-7.5, -1.5, -1.5))
        self.assertEqual((b["base_line"], b["teased_line"]), (55.5, 49.5))
        self.assertEqual(a["market"], "teaser_leg")
        rows2, _ = self.run_one("Teaser: Ole Miss -1.5 teased, Kansas State at Colorado Under 61.5 teased")
        self.assertEqual((rows2[0]["base_line"], rows2[0]["teased_line"]), (-7.5, -1.5))
        self.assertEqual((rows2[1]["base_line"], rows2[1]["teased_line"]), (55.5, 61.5))

    def test_ticket_probability_for_parlay(self):
        rows, _ = self.run_one("Parlay: Ole Miss -10.5, Kansas State at Colorado Over 55.5")
        self.assertAlmostEqual(float(rows[0]["ticket_prob"]), 0.6 * 0.58, 3)
        self.assertAlmostEqual(float(rows[0]["ticket_break_even"]), 0.2744, 3)


class Grading(unittest.TestCase):
    def test_graded_only_on_locked_line(self):
        by = {g["_id"]: g for g in GAMES}
        t, _ = sc.parse_lines("Buffalo -3\nBuffalo -4.5\nBaltimore at Buffalo Over 43.5\nBuffalo ML -150")
        rows, _ = sc.compare(t, GAMES, NOW, None, TODAY, None)
        g = sc.grade_log(rows, by)
        self.assertEqual([r["leg_result"] for r in g], ["Win", "Loss", "Win", "Win"])   # won by 4: -3 wins, -4.5 loses
        self.assertEqual(g[0]["imported_line"], -3.0)

    def test_teaser_and_parlay_tickets(self):
        by = {g["_id"]: g for g in GAMES}
        t, _ = sc.parse_lines("Teaser: Buffalo -7.5, Baltimore at Buffalo Over 49.5\nParlay: Buffalo -3, Baltimore at Buffalo Under 40")
        rows, _ = sc.compare(t, GAMES, NOW, None, TODAY, None)
        g = sc.grade_log(rows, by)
        self.assertEqual({r["ticket_result"] for r in g[:2]}, {"Win"})     # -1.5 and over 43.5 both win
        self.assertEqual({r["ticket_result"] for r in g[2:]}, {"Loss"})

    def test_pending_game_stays_pending(self):
        by = {g["_id"]: g for g in GAMES}
        t, _ = sc.parse_lines("Ole Miss -10.5")
        rows, _ = sc.compare(t, GAMES, NOW, None, TODAY, None)
        self.assertEqual(sc.grade_log(rows, by)[0]["leg_result"], "pending")


if __name__ == "__main__":
    unittest.main()


class Report(unittest.TestCase):
    def test_report_pieces(self):
        import intelligence_report as ir
        by = {g["_id"]: g for g in GAMES}
        t, _ = sc.parse_lines("Buffalo -3\nBaltimore at Buffalo Over 43.5")
        rows, _ = sc.compare(t, GAMES, NOW, pricer, TODAY, None)
        g = sc.grade_log(rows, by)
        for r in g:
            r["model_result"] = ir._model_result(r, by.get(r["record_id"]))
        summ = {m["market"]: m for m in ir.by_market_summary(g, by)}
        self.assertEqual(summ["spread"]["you_w"], 1)
        self.assertEqual(summ["total"]["model_w"], 1)
        text = "\n".join(ir.render_markets({"latest": None, "scorecards": {}, "changes": [], "notes": []}))
        self.assertIn("Every bet type", text)
        tt = ir.timing_table([dict(r, lead_days=-2, movement_for_you=0.5) for r in g])
        self.assertEqual(tt[2]["n"], 0)
