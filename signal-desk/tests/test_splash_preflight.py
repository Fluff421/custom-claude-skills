import copy
import datetime as dt
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import splash_preflight as pf

NOW = dt.datetime(2026, 11, 16, 21, 0, tzinfo=dt.timezone.utc)


def lines():
    return {"schema": pf.LINES, "source": "Splash Sports Lines",
            "date_code": "SPL-L-20261116-1356",
            "extracted_at_central": "2026-11-16 13:56:00 CST",
            "extracted_at_utc": "2026-11-16T19:56:00Z",
            "game_count": {"NFL": 1, "NCAAF": 1}, "notes": [], "warnings": [],
            "games": [
                {"league": "NCAAF", "away_team": "Eastern Michigan", "home_team": "Western Michigan",
                 "home_away_certain": True, "kickoff_as_shown": "Tue, Nov 17, 6:00 PM EST",
                 "kickoff_central": "2026-11-17 17:00", "kickoff_tz": "CST",
                 "away_spread": 14.5, "home_spread": -14.5, "total": 46.5,
                 "away_spread_price": 100, "home_spread_price": 100, "over_price": 100,
                 "under_price": 100, "away_ml": 500, "home_ml": -690, "other_markets": []},
                {"league": "NFL", "away_team": "Bills", "home_team": "Jets",
                 "home_away_certain": True, "kickoff_as_shown": "Sun, Nov 22, 1:00 PM EST",
                 "kickoff_central": "2026-11-22 12:00", "kickoff_tz": "CST",
                 "away_spread": -3, "home_spread": 3, "total": 44.5,
                 "away_spread_price": 100, "home_spread_price": 100, "over_price": 100,
                 "under_price": 100, "away_ml": -150, "home_ml": 130, "other_markets": []}]}


def picks():
    return {"schema": pf.PICKS, "source": "Splash Sports Picks",
            "date_code": "SPL-C-20261116-1341",
            "extracted_at_central": "2026-11-16 13:41:00 CST",
            "extracted_at_utc": "2026-11-16T19:41:00Z",
            "page_type": "completed", "ticket_count": 1, "notes": [], "warnings": [],
            "tickets": [{
                "ticket_id": "src-1", "ticket_type": "parlay",
                "ticket_time_as_shown": "Sat, Nov 14, 8:02 PM EST",
                "placed_at_central": None, "legs": [
                    {"league": "NCAAF", "away_team": "Tulane", "home_team": "Rice",
                     "home_away_certain": True, "game_date_central": "2026-11-14",
                     "kickoff_central": None, "kickoff_tz": None, "kickoff_as_shown": None,
                     "market": "moneyline", "selection": "Tulane", "line": None, "price": -200},
                    {"league": "NCAAF", "away_team": "Auburn", "home_team": "Mississippi State",
                     "home_away_certain": True, "game_date_central": "2026-11-14",
                     "kickoff_central": None, "kickoff_tz": None, "kickoff_as_shown": None,
                     "market": "spread", "selection": "Auburn", "line": -2.5, "price": 100}]}]}


def run(d):
    return pf.lint(json.dumps(d, separators=(",", ":")).encode(), NOW)


def messages(report):
    return " | ".join(m for level, _, m in report.items if level == "ERROR")


class PreflightTests(unittest.TestCase):
    def test_clean_lines_and_picks_pass(self):
        for d in (lines(), picks()):
            r, _ = run(d)
            self.assertEqual(r.errors, [], messages(r))

    def test_integer_game_count_is_rejected_with_the_array_counts(self):
        d = lines()
        d["game_count"] = 64
        r, _ = run(d)
        self.assertIn('{"NFL": 1, "NCAAF": 1}', messages(r))

    def test_game_count_mismatch(self):
        d = lines()
        d["game_count"] = {"NFL": 1, "NCAAF": 5}
        self.assertIn("games array has", messages(run(d)[0]))

    def test_source_zone_in_kickoff_tz_is_rejected(self):
        d = picks()
        d["tickets"][0]["legs"][1]["kickoff_tz"] = "EST"
        self.assertIn("kickoff_tz 'EST' is not allowed", messages(run(d)[0]))

    def test_wrong_central_label_for_date(self):
        d = lines()
        d["games"][0]["kickoff_tz"] = "CDT"
        self.assertIn("wrong for 2026-11-17; use CST", messages(run(d)[0]))

    def test_ticket_time_copied_as_kickoff(self):
        d = picks()
        d["tickets"][0]["legs"][0]["kickoff_as_shown"] = "Sat, Nov 14, 8:02 PM EST"
        self.assertIn("placement/settlement time", messages(run(d)[0]))

    def test_moneyline_without_price(self):
        d = picks()
        d["tickets"][0]["legs"][0]["price"] = None
        self.assertIn("moneyline needs its actual American price", messages(run(d)[0]))

    def test_any_warning_blocks(self):
        d = picks()
        d["warnings"] = ["game dates inferred from headers"]
        self.assertIn("blocks import", messages(run(d)[0]))

    def test_sunday_college_date_is_a_check_not_an_error(self):
        d = picks()
        d["tickets"][0]["legs"][1]["game_date_central"] = "2026-11-15"
        r, _ = run(d)
        self.assertEqual(r.errors, [], messages(r))
        self.assertTrue(any(level == "CHECK" and "Sunday" in m for level, _, m in r.items))

    def test_clock_fields_must_be_the_same_instant(self):
        d = lines()
        d["extracted_at_central"] = "2026-11-16 14:56:00 CST"
        self.assertIn("same instant", messages(run(d)[0]))

    def test_date_code_must_equal_extraction_minute(self):
        d = lines()
        d["date_code"] = "SPL-L-20261116-1400"
        self.assertIn("Central extraction minute", messages(run(d)[0]))

    def test_uncertain_orientation_and_bad_spreads(self):
        d = lines()
        d["games"][0]["home_away_certain"] = False
        d["games"][1]["home_spread"] = -3
        text = messages(run(d)[0])
        self.assertIn("home_away_certain must be true", text)
        self.assertIn("must equal minus home_spread", text)

    def test_teaser_needs_teased_line(self):
        d = picks()
        t = d["tickets"][0]
        t["ticket_type"] = "teaser"
        t["legs"] = [copy.deepcopy(t["legs"][1]), copy.deepcopy(t["legs"][1])]
        t["legs"][1]["selection"] = "Mississippi State"
        for leg in t["legs"]:
            leg["teased_line"] = None
        self.assertIn("teased_line", messages(run(d)[0]))

    def test_stale_capture_is_rejected(self):
        d = lines()
        r, _ = pf.lint(json.dumps(d).encode(), NOW + dt.timedelta(hours=30))
        self.assertIn("importer limit is 24 h", messages(r))

    def test_not_json(self):
        r, _ = pf.lint(b"```json\n{}\n```", NOW)
        self.assertIn("not valid JSON", messages(r))


if __name__ == "__main__":
    unittest.main()
