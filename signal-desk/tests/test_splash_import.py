import copy
import datetime as dt
import json
import pathlib
import sys
import unittest
import tempfile
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import splash_import as si

NOW = dt.datetime(2026, 11, 10, 6, tzinfo=dt.timezone.utc)
GAME = {"_id": "r1", "League": "NFL", "Date": "2026-11-15",
        "Game": "Tampa Bay Buccaneers @ Chicago Bears",
        "Away Team": "Tampa Bay Buccaneers", "Home Team": "Chicago Bears",
        "Vegas Implied Home Margin": 6.5, "Over/Under Line": 47.5}

def lines():
    return {"schema": si.LINES, "source": "Splash Sports Lines",
            "date_code": "SPL-L-20261109-1916", "extracted_at_utc": "2026-11-10T01:16:00Z",
            "game_count": {"NFL": 1}, "games": [
                {"league": "NFL", "away_team": GAME["Away Team"], "home_team": GAME["Home Team"],
                 "home_spread": -6.5, "away_spread": 6.5, "total": 47.5,
                 "kickoff_central": "2026-11-15 19:20"}]}

def picks():
    return {"schema": si.PICKS, "source": "Splash Sports Picks",
            "date_code": "SPL-P-20261109-1916", "extracted_at_utc": "2026-11-10T01:16:00Z",
            "page_type": "pending", "ticket_count": 1, "warnings": [], "tickets": [
                {"ticket_id": "source-ticket-1", "ticket_type": "parlay", "payout_multiplier": "+300",
                 "legs": [
                     {"league": "NFL", "away_team": GAME["Away Team"], "home_team": GAME["Home Team"],
                      "market": "spread", "selection": GAME["Away Team"], "line": 6.5,
                      "kickoff_central": "2026-11-15 19:20"},
                     {"league": "NFL", "away_team": GAME["Away Team"], "home_team": GAME["Home Team"],
                      "market": "total", "selection": "Over", "line": 47.5,
                      "kickoff_central": "2026-11-15 19:20"}]}]}

class Imports(unittest.TestCase):
    def plan(self, d, games=None, previous=None, log=None):
        return si.plan(d, games if games is not None else [GAME], previous or [], log or [], NOW)

    def test_valid_lines(self):
        self.assertEqual(self.plan(lines())["expected_rows"], 1)

    def test_established_feed_aliases_bind_remaining_college_games(self):
        for away, home, ledger_away, ledger_home in (
            ("Louisiana", "Louisiana-Monroe", "Louisiana", "UL Monroe"),
            ("Duke", "Miami (FL)", "Duke", "Miami"),
            ("Appalachian State", "Marshall", "App State", "Marshall"),
        ):
            with self.subTest(away=away, home=home):
                g = {"league": "NCAAF", "away_team": away, "home_team": home,
                     "kickoff_central": "2026-11-14 15:00", "home_away_certain": True}
                f = {"_id": "college", "League": "NCAAF", "Date": "2026-11-14",
                     "Away Team": ledger_away, "Home Team": ledger_home}
                self.assertEqual(si.matching(g, [f])["_id"], "college")
                with self.assertRaisesRegex(si.Rejected, "orientation"):
                    si.matching(dict(g, away_team=home, home_team=away), [f])
                with self.assertRaisesRegex(si.Rejected, "matches 2"):
                    si.matching(g, [f, dict(f, _id="duplicate")])

    def test_alias_does_not_bind_a_different_opponent_or_league(self):
        g = {"league": "NCAAF", "away_team": "Duke", "home_team": "Miami (FL)",
             "kickoff_central": "2026-11-14 15:00"}
        f = {"_id": "college", "League": "NCAAF", "Date": "2026-11-14",
             "Away Team": "Virginia", "Home Team": "Miami"}
        for wrong in (f, dict(f, **{"League": "NFL", "Away Team": "Duke"}),
                      dict(f, **{"Date": "2026-11-20", "Away Team": "Duke"})):
            with self.subTest(wrong=wrong), self.assertRaisesRegex(si.Rejected, "matches 0"):
                si.matching(g, [wrong])

    def test_four_hours_is_warning_not_line_rejection_limit(self):
        for hours, warning in ((4, False), (4.01, True), (24, True)):
            with self.subTest(hours=hours):
                d = lines()
                d["extracted_at_utc"] = (NOW - dt.timedelta(hours=hours)).isoformat()
                result = self.plan(d)
                self.assertEqual(result["expected_rows"], 1)
                self.assertEqual(bool(result["freshness_warning"]), warning)
        d = lines()
        d["extracted_at_utc"] = (NOW - dt.timedelta(hours=24, seconds=1)).isoformat()
        with self.assertRaisesRegex(si.Rejected, "24 hours"):
            self.plan(d)

    def test_count_mismatch_stays_rejected_after_old_games_final(self):
        d = lines()
        d["game_count"] = {"NFL": 16, "NCAAF": 63}
        with self.assertRaisesRegex(si.Rejected, "game_count"):
            self.plan(d, previous=[{"record_id": "old"}])

    def test_zero_match_rejected(self):
        with self.assertRaisesRegex(si.Rejected, "matches 0"):
            self.plan(lines(), games=[])

    def test_reversed_neutral_site_rejected(self):
        f = dict(GAME, **{"Home Team": GAME["Away Team"], "Away Team": GAME["Home Team"], "Neutral Site": True})
        with self.assertRaisesRegex(si.Rejected, "orientation"):
            self.plan(lines(), games=[f])

    def test_ambiguous_rejected(self):
        with self.assertRaisesRegex(si.Rejected, "matches 2"):
            self.plan(lines(), games=[GAME, dict(GAME, _id="r2")])

    def test_bad_date_rejected(self):
        d = lines()
        d["games"][0]["kickoff_central"] = "2026-11-32 19:20"
        with self.assertRaises(si.Rejected):
            self.plan(d)

    def test_naive_timestamp_rejected(self):
        d = lines()
        d["extracted_at_utc"] = "2026-11-10T01:16:00"
        with self.assertRaisesRegex(si.Rejected, "timezone"):
            self.plan(d)

    def test_future_timestamp_rejected(self):
        d = lines()
        d["extracted_at_utc"] = "2026-11-11T01:16:00Z"
        with self.assertRaisesRegex(si.Rejected, "future"):
            self.plan(d)

    def test_stale_rejected(self):
        d = lines()
        d["extracted_at_utc"] = "2026-11-08T01:16:00Z"
        with self.assertRaisesRegex(si.Rejected, "24"):
            self.plan(d)

    def test_pending_picks_keep_twelve_hour_limit(self):
        d = picks()
        d["extracted_at_utc"] = "2026-11-09T17:00:00Z"
        with self.assertRaisesRegex(si.Rejected, "12 hours"):
            self.plan(d)

    def test_path_traversal_rejected(self):
        d = lines()
        d["date_code"] = "../../bad"
        with self.assertRaisesRegex(si.Rejected, "date_code"):
            self.plan(d)

    def test_nonfinite_rejected(self):
        d = lines()
        d["games"][0]["total"] = float("nan")
        with self.assertRaisesRegex(si.Rejected, "finite"):
            self.plan(d)

    def test_duplicate_game_rejected(self):
        d = lines()
        d["games"] *= 2
        d["game_count"]["NFL"] = 2
        with self.assertRaisesRegex(si.Rejected, "duplicate game"):
            self.plan(d)

    def test_unknown_schema_rejected(self):
        with self.assertRaisesRegex(si.Rejected, "schema"):
            self.plan({"schema": "other"})

    def test_native_picks_full_names(self):
        p = self.plan(picks())
        self.assertEqual(p["expected_rows"], 2)
        self.assertEqual(p["tickets"][0]["text"], "Parlay: Tampa Bay Buccaneers +6.5, Tampa Bay Buccaneers at Chicago Bears Over 47.5")
        self.assertEqual(p["tickets"][0]["metadata"]["payout_multiplier"], "+300")

    def test_changed_existing_source_ticket_requires_review(self):
        d = picks()
        old = self.plan(d)["tickets"][0]["fingerprint"]
        d["tickets"][0]["legs"][0]["line"] = 7.5
        with self.assertRaisesRegex(si.Rejected, "source ticket_id has changed"):
            si.plan(d, [GAME], [], [], NOW, {"source-ticket-1": old})

    def test_moneyline_price_is_part_of_ticket_identity(self):
        d = picks()
        t = d["tickets"][0]
        t["ticket_type"] = "single"
        t["legs"] = [dict(t["legs"][0], market="moneyline", price=150)]
        old = self.plan(d)["tickets"][0]["fingerprint"]
        t["legs"][0]["price"] = 175
        self.assertNotEqual(old, self.plan(d)["tickets"][0]["fingerprint"])

    def test_wrong_central_season_label_rejected(self):
        d = lines()
        d["games"][0]["kickoff_tz"] = "CDT"
        with self.assertRaisesRegex(si.Rejected, "Central"):
            self.plan(d)

    def test_null_teased_line_rejected(self):
        d = picks()
        d["tickets"][0]["ticket_type"] = "teaser"
        with self.assertRaisesRegex(si.Rejected, "teased_line"):
            self.plan(d)

    def test_explicit_teased_suffix(self):
        d = picks()
        d["tickets"][0]["ticket_type"] = "teaser"
        for leg in d["tickets"][0]["legs"]:
            leg["teased_line"] = leg["line"]
        self.assertEqual(self.plan(d)["tickets"][0]["text"].count("teased"), 2)

    def test_wrong_week_rejected(self):
        d = picks()
        for leg in d["tickets"][0]["legs"]:
            leg["kickoff_central"] = "2026-11-08 19:20"
        with self.assertRaisesRegex(si.Rejected, "matches 0"):
            self.plan(d)

    def test_missing_date_rejected_not_nearest_today(self):
        d = picks()
        d["tickets"][0]["legs"][0]["kickoff_central"] = None
        with self.assertRaisesRegex(si.Rejected, "Central"):
            self.plan(d)

    def test_legacy_ticket_dedup(self):
        rows = [{"ticket_id": "old", "ticket_type": "parlay", "record_id": "r1",
                 "market": "spread", "side": "away", "locked_line": "6.5"},
                {"ticket_id": "old", "ticket_type": "parlay", "record_id": "r1",
                 "market": "total", "side": "over", "locked_line": "47.5"}]
        p = self.plan(picks(), log=rows)
        self.assertEqual(p["expected_rows"], 0)
        self.assertEqual(len(p["duplicates"]), 1)

    def test_ticket_count_rejected(self):
        d = picks()
        d["ticket_count"] = 2
        with self.assertRaisesRegex(si.Rejected, "ticket_count"):
            self.plan(d)

    def test_warnings_not_silently_discarded(self):
        d = picks()
        d["warnings"] = ["teased line uncertain"]
        with self.assertRaisesRegex(si.Rejected, "warnings"):
            self.plan(d)

    def test_source_id_collision_rejected(self):
        d = picks()
        d["tickets"].append(copy.deepcopy(d["tickets"][0]))
        d["ticket_count"] = 2
        with self.assertRaisesRegex(si.Rejected, "ticket_id"):
            self.plan(d)

    def test_reconciliation_uses_recorded_line_not_early_line(self):
        f = dict(GAME, **{"Home Score": 30, "Away Score": 27})
        row = {"ticket_id": "x", "ticket_type": "single", "record_id": "r1", "market": "spread",
               "side": "away", "locked_line": "2.5", "status": "upcoming"}
        r = si.reconcile([f], [row])
        self.assertEqual(r["leg_results"], {"Loss": 1})
        self.assertEqual(r["stale_capture_status_count"], 1)
        self.assertNotIn("leg_result", row)

    def test_execute_native_picks_and_idempotent_replay(self):
        import intelligence_report as ir
        import picks as pk
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            inbox = root / "intelligence/splash_import/inbox"
            inbox.mkdir(parents=True)
            d = picks()
            path = inbox / (d["date_code"] + ".json")
            raw = json.dumps(d).encode()
            path.write_bytes(raw)
            patches = [
                mock.patch.object(si, "HERE", root),
                mock.patch.object(si, "load_context", return_value=("redacted", "base", [GAME], [])),
                mock.patch.object(si.sl, "LOG", str(root/"intelligence/splash_lines_log.csv")),
                mock.patch.object(ir, "fetch", return_value=[]),
                mock.patch.object(pk, "load_params", return_value={}),
                mock.patch.object(pk, "graded_counts", return_value={}),
                mock.patch.object(si.sc, "make_pricer", return_value=lambda *a, **k: {}),
            ]
            import contextlib
            with contextlib.ExitStack() as stack:
                for p in patches:
                    stack.enter_context(p)
                si.execute(path, now=NOW)
                receipt = json.loads((root/"intelligence/splash_import/receipts"/(d["date_code"]+".json")).read_text())
                self.assertEqual(receipt["actual_new_rows"], 2)
                self.assertEqual(receipt["airtable_writes"], 0)
                self.assertEqual(receipt["ticket_metadata"][0]["payout_multiplier"], "+300")
                self.assertEqual((root/"intelligence/splash_picks/raw"/path.name).read_bytes(), raw)
                log = root/"intelligence/splash_picks_log.csv"
                before = log.read_bytes()
                path.write_bytes(raw)
                si.execute(path, check_only=True, now=NOW)
                self.assertTrue(path.exists(), "dry run must not move a replay input")
                si.execute(path, now=NOW)
                self.assertEqual(log.read_bytes(), before)
                text = root/"intelligence/splash_picks/processed"/(d["date_code"]+".txt")
                self.assertIn("Parlay: Tampa Bay Buccaneers +6.5", text.read_text())
                d["tickets"][0]["legs"][0]["line"] = 7.5
                d["date_code"] = "SPL-P-20261109-1917"
                path = inbox/(d["date_code"]+".json")
                path.write_text(json.dumps(d))
                with self.assertRaisesRegex(si.Rejected, "source ticket_id has changed"):
                    si.execute(path, now=NOW)
                self.assertEqual(log.read_bytes(), before)

    def test_execute_lines_builds_reports_and_append_only_snapshot(self):
        import contextlib
        import intelligence_report as ir
        import picks as pk
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            d = lines()
            path = root/"intelligence/splash_import/inbox"/(d["date_code"]+".json")
            path.parent.mkdir(parents=True)
            raw = json.dumps(d).encode()
            path.write_bytes(raw)
            patches = [
                mock.patch.object(si, "HERE", root),
                mock.patch.object(si, "load_context", return_value=("redacted", "base", [GAME], [])),
                mock.patch.object(si.sl, "LOG", str(root/"intelligence/splash_lines_log.csv")),
                mock.patch.object(si.sl, "DIR", str(root/"intelligence/splash_lines")),
                mock.patch.object(si.sl, "PICKS_LATEST", str(root/"missing-picks.json")),
                mock.patch.object(si.sl, "MARKET_LOG", str(root/"missing-market.csv")),
                mock.patch.object(si.sp, "DIR", str(root/"intelligence/splash_pricecheck")),
                mock.patch.object(ir, "fetch", return_value=[]),
                mock.patch.object(pk, "load_params", return_value={}),
                mock.patch.object(pk, "graded_counts", return_value={}),
                mock.patch.object(si.sc, "make_pricer", return_value=lambda *a, **k: {}),
                mock.patch.object(ir, "central_today", return_value=NOW.date()),
            ]
            with contextlib.ExitStack() as stack:
                for patch in patches:
                    stack.enter_context(patch)
                si.execute(path, now=NOW)
                log = root/"intelligence/splash_lines_log.csv"
                rows = si.sl.read_csv(str(log))
                self.assertEqual(len(rows), 1)
                self.assertEqual(float(rows[0]["home_margin"]), 6.5)
                self.assertEqual(float(rows[0]["total"]), 47.5)
                self.assertTrue((root/"intelligence/splash_lines/latest.md").exists())
                check = json.loads((root/"intelligence/splash_pricecheck/latest.json").read_text())
                self.assertEqual(len(check["games"]), 1)
                self.assertEqual((root/"intelligence/splash_lines/raw"/path.name).read_bytes(), raw)
                before = log.read_bytes()
                path.write_bytes(raw)
                si.execute(path, now=NOW)
                self.assertEqual(log.read_bytes(), before)
                # The first snapshot remains unchanged when another valid capture arrives.
                d["date_code"] = "SPL-L-20261109-1917"
                d["games"][0]["home_spread"] = -7.5
                d["games"][0]["away_spread"] = 7.5
                path = path.parent/(d["date_code"]+".json")
                path.write_text(json.dumps(d))
                si.execute(path, now=NOW)
                rows = si.sl.read_csv(str(log))
                self.assertEqual(len(rows), 2)
                self.assertEqual(float(rows[0]["home_margin"]), 6.5)
                self.assertEqual(float(rows[1]["home_margin"]), 7.5)
                self.assertEqual(rows[1]["snapshot_kind"], "movement")

    def test_rejected_execution_changes_no_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            path = root/"intelligence/splash_import/inbox/SPL-L-20261109-1916.json"
            path.parent.mkdir(parents=True)
            d = lines()
            d["game_count"]["NFL"] = 16
            path.write_text(json.dumps(d))
            with mock.patch.object(si, "HERE", root), \
                 mock.patch.object(si, "load_context", return_value=("redacted", "base", [GAME], [])), \
                 mock.patch.object(si.sl, "LOG", str(root/"missing.csv")):
                with self.assertRaises(si.Rejected):
                    si.execute(path)
            self.assertEqual([p for p in root.rglob("*") if p.is_file()], [path])

if __name__ == "__main__":
    unittest.main()
