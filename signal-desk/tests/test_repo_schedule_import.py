"""Repository-only schedule contracts. Fixtures are synthetic, never owner data."""
import contextlib
import copy
import datetime as dt
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from test_splash_import import GAME, NOW, lines, picks
import splash_import as si
import intelligence_report as ir
import picks as pk


class RepoScheduleImports(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.ledger = []
        self.real_make_pricer = si.sc.make_pricer
        self.pricer = mock.Mock(side_effect=AssertionError("unpriced game reached model"))
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        patches = [
            mock.patch.object(si, "HERE", self.root),
            mock.patch.object(si, "load_context", side_effect=lambda: (
                "redacted", "base", self.ledger,
                si.sl.read_csv(str(self.root / "intelligence/splash_picks_log.csv")))),
            mock.patch.object(si.sl, "LOG", str(self.root / "intelligence/splash_lines_log.csv")),
            mock.patch.object(si.sl, "DIR", str(self.root / "intelligence/splash_lines")),
            mock.patch.object(si.sl, "PICKS_LATEST", str(self.root / "missing-picks.json")),
            mock.patch.object(si.sl, "MARKET_LOG", str(self.root / "missing-market.csv")),
            mock.patch.object(si.sp, "DIR", str(self.root / "intelligence/splash_pricecheck")),
            mock.patch.object(ir, "fetch", return_value=[]),
            mock.patch.object(pk, "load_params", return_value={}),
            mock.patch.object(pk, "graded_counts", return_value={}),
            mock.patch.object(si.sc, "make_pricer", return_value=self.pricer),
            mock.patch.object(ir, "central_today", return_value=NOW.date()),
        ]
        for patch in patches:
            self.stack.enter_context(patch)

    def file(self, d):
        path = self.root / "intelligence/splash_import/inbox" / (d["date_code"] + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(d))
        return path

    def line_dump(self):
        d = lines()
        d["games"][0]["home_away_certain"] = True
        return d

    def receipt(self, d):
        return json.loads((self.root / "intelligence/splash_import/receipts" /
                           (d["date_code"] + ".json")).read_text())

    def schedule(self):
        return json.loads((self.root / "intelligence/splash_import/schedule.json").read_text())

    def seed(self):
        d = self.line_dump()
        si.execute(self.file(d), now=NOW)
        return d, self.receipt(d)["matches"][0]

    def test_new_week_lines_import_without_ledger_rows_and_stay_unpriced(self):
        d, rid = self.seed()
        self.assertTrue(rid.startswith("repo-game:"))
        self.assertEqual(self.receipt(d)["airtable_writes"], 0)
        self.assertEqual(self.receipt(d)["actual_new_rows"], 1)
        self.assertEqual(self.receipt(d)["reference_matches"][0]["reference_origin"], "repository")
        row = self.schedule()["games"][0]
        self.assertEqual(row["reference_id"], rid)
        self.assertEqual(row["first_source"]["date_code"], d["date_code"])
        self.assertIsNone(row["ledger_record_id"])
        check = json.loads((self.root / "intelligence/splash_pricecheck/latest.json").read_text())
        self.assertEqual(check["games"][0]["model_status"], "unpriced")
        self.assertNotIn("spread", check["games"][0])
        self.assertIn("unpriced", (self.root / "intelligence/splash_pricecheck/latest.md").read_text())
        self.pricer.assert_not_called()

    def test_check_only_and_invalid_count_do_not_create_schedule(self):
        d = self.line_dump()
        path = self.file(d)
        si.execute(path, check_only=True, now=NOW)
        self.assertEqual([p for p in self.root.rglob("*") if p.is_file()], [path])
        d["game_count"]["NFL"] = 2
        path = self.file(d)
        with self.assertRaisesRegex(si.Rejected, "game_count"):
            si.execute(path, now=NOW)
        self.assertEqual([p for p in self.root.rglob("*") if p.is_file()], [path])

    def test_movement_keeps_reference_and_first_quote(self):
        d, rid = self.seed()
        first = copy.deepcopy(self.schedule()["games"][0]["first_source"])
        d["date_code"] = "SPL-L-20261109-1917"
        d["extracted_at_utc"] = "2026-11-10T01:17:00Z"
        d["games"][0]["home_spread"] = -7.5
        d["games"][0]["away_spread"] = 7.5
        si.execute(self.file(d), now=NOW)
        self.assertEqual(self.receipt(d)["matches"], [rid])
        self.assertEqual(self.schedule()["games"][0]["first_source"], first)
        rows = si.sl.read_csv(si.sl.LOG)
        self.assertEqual([float(r["home_margin"]) for r in rows], [6.5, 7.5])
        self.assertEqual(rows[1]["snapshot_kind"], "movement")
        self.assertEqual(len(self.schedule()["games"][0]["captures"]), 2)

    def test_picks_use_seeded_schedule_without_inventing_model_or_results(self):
        _, rid = self.seed()
        d = picks()
        d["page_type"] = "completed"
        d["tickets"][0]["reported_result"] = "Win"
        si.execute(self.file(d), now=NOW)
        receipt = self.receipt(d)
        self.assertEqual(receipt["actual_new_rows"], 2)
        self.assertEqual(set(receipt["matches"]), {rid})
        rows = si.sl.read_csv(str(self.root / "intelligence/splash_picks_log.csv"))
        self.assertTrue(all(r["model_status"] == "unpriced" for r in rows))
        self.assertTrue(all(r.get("model_prob_lock", "") == "" for r in rows))
        self.assertTrue(all(r.get("ticket_prob", "") == "" for r in rows))
        outcomes = json.loads((self.root / "intelligence/splash_import/reconciliation/latest.json").read_text())
        self.assertEqual(outcomes["leg_results"], {"pending": 2})
        self.pricer.assert_not_called()

    def test_picks_cannot_create_an_unseen_game(self):
        d = picks()
        path = self.file(d)
        with self.assertRaisesRegex(ValueError, "no.*schedule|matches 0"):
            si.execute(path, now=NOW)
        self.assertFalse((self.root / "intelligence/splash_import/schedule.json").exists())

    def test_later_ledger_binding_keeps_identity_and_uses_real_scores(self):
        d, rid = self.seed()
        self.ledger = [dict(GAME, **{"Home Score": 30, "Away Score": 20})]
        d = picks()
        si.execute(self.file(d), now=NOW)
        self.assertEqual(set(self.receipt(d)["matches"]), {rid})
        self.assertEqual(self.schedule()["games"][0]["ledger_record_id"], GAME["_id"])
        outcomes = json.loads((self.root / "intelligence/splash_import/reconciliation/latest.json").read_text())
        self.assertEqual(outcomes["leg_results"], {"Win": 1, "Loss": 1})

    def test_reversed_or_ambiguous_ledger_is_not_a_missing_game_fallback(self):
        for ledger in (
            [dict(GAME, **{"Home Team": GAME["Away Team"], "Away Team": GAME["Home Team"]})],
            [GAME, dict(GAME, _id="r2")],
        ):
            with self.subTest(ledger=ledger):
                self.ledger = ledger
                d = self.line_dump()
                with self.assertRaisesRegex(si.Rejected, "orientation|matches 2"):
                    si.execute(self.file(d), now=NOW)
                self.assertFalse((self.root / "intelligence/splash_import/schedule.json").exists())

    def test_new_reference_requires_explicit_orientation(self):
        d = lines()
        with self.assertRaisesRegex(ValueError, "certain|orientation"):
            si.execute(self.file(d), now=NOW)
        self.assertFalse((self.root / "intelligence/splash_import/schedule.json").exists())

    def test_ambiguous_short_team_is_not_missing_schedule_fallback(self):
        self.ledger = [GAME, dict(GAME, _id="r2", **{
            "Home Team": "Example Bears", "Away Team": "Example Visitors"})]
        d = self.line_dump()
        d["games"][0].update(away_team="Buccaneers", home_team="Bears")
        with self.assertRaisesRegex(ValueError, "ambiguous short team"):
            si.execute(self.file(d), now=NOW)
        self.assertFalse((self.root / "intelligence/splash_import/schedule.json").exists())

    def test_reader_adapter_preserves_repo_identity_without_double_match(self):
        _, rid = self.seed()
        path = self.root / "intelligence/splash_import/schedule.json"
        before = path.read_bytes()
        fields = si.sl.with_repository_schedule([GAME], path=path)
        self.assertEqual([f["_id"] for f in fields], [rid])
        self.assertEqual(fields[0]["_ledger_record_id"], GAME["_id"])
        aliases = si.sl.with_repository_schedule([GAME], path=path, keep_ledger_aliases=True)
        self.assertEqual({f["_id"] for f in aliases}, {rid, GAME["_id"]})
        self.assertEqual(path.read_bytes(), before, "read-only adapter must not save its binding")

    def test_later_ledger_binding_does_not_duplicate_ticket(self):
        self.seed()
        d = picks()
        si.execute(self.file(d), now=NOW)
        self.ledger = [GAME]
        d["date_code"] = "SPL-P-20261109-1917"
        si.execute(self.file(d), now=NOW)
        self.assertEqual(self.receipt(d)["actual_new_rows"], 0)
        self.assertEqual(len(self.receipt(d)["duplicates"]), 1)
        self.assertEqual(len(si.sl.read_csv(str(self.root / "intelligence/splash_picks_log.csv"))), 2)

    def test_unpriced_guards_cover_every_market_and_teaser(self):
        f = dict(GAME, _model_status="unpriced")
        # Use the real factory, not the integration fixture's stub.
        from splash_compare import mk
        with mock.patch.object(mk, "project_game", side_effect=AssertionError("fabricated projection")):
            pricer = self.real_make_pricer({}, {}, NOW.isoformat())
            for market, side in (("spread", "home"), ("total", "over"), ("moneyline", "away")):
                self.assertEqual(pricer(f, market, side, 47.5, -110), {})
                result = si.sp.check_game(f, {"home_margin": 6.5, "total": 47.5}, self.pricer, {}, False)
                self.assertEqual(result["model_status"], "unpriced")
                self.assertNotIn(market, result)
            for market in ("spread", "total"):
                self.assertIsNone(si.sc.teaser_leg_prob(f, {"market": market}, 47.5, 41.5, "over", {}, False))

    def test_reconciliation_refresh_reads_later_scores_without_rewriting_log(self):
        _, rid = self.seed()
        d = picks()
        si.execute(self.file(d), now=NOW)
        path = self.root / "intelligence/splash_picks_log.csv"
        before = path.read_bytes()
        self.ledger = [dict(GAME, **{"Home Score": 30, "Away Score": 20})]
        si.reconcile_only()
        outcome = json.loads((self.root / "intelligence/splash_import/reconciliation/latest.json").read_text())
        self.assertEqual(outcome["leg_results"], {"Win": 1, "Loss": 1})
        self.assertEqual({r["record_id"] for r in outcome["legs"]}, {rid})
        self.assertEqual(path.read_bytes(), before)

    def test_full_owner_names_resolve_against_short_source_names(self):
        d = self.line_dump()
        d["games"][0].update(away_team="Buccaneers", home_team="Bears")
        si.execute(self.file(d), now=NOW)
        rid = self.receipt(d)["matches"][0]
        p = picks()
        si.execute(self.file(p), now=NOW)
        self.assertEqual(set(self.receipt(p)["matches"]), {rid})
        r = self.schedule()["games"][0]
        self.assertEqual(r["away_team"], "Buccaneers", "initial source identity must not be rewritten")
        self.assertEqual(r["display_away_team"], GAME["Away Team"])
        self.assertEqual(r["name_observations"][0]["date_code"], p["date_code"])
        self.assertIn("Tampa Bay Buccaneers +6.5",
                      (self.root / "intelligence/splash_picks/processed" / (p["date_code"] + ".txt")).read_text())

    def test_short_name_expansion_cannot_hide_reversed_orientation(self):
        d = self.line_dump()
        d["games"][0].update(away_team="Buccaneers", home_team="Bears")
        si.execute(self.file(d), now=NOW)
        p = picks()
        for leg in p["tickets"][0]["legs"]:
            leg["away_team"], leg["home_team"] = leg["home_team"], leg["away_team"]
        with self.assertRaisesRegex(ValueError, "orientation"):
            si.execute(self.file(p), now=NOW)
        self.assertEqual(len(self.schedule()["games"]), 1)
        self.assertFalse((self.root / "intelligence/splash_picks_log.csv").exists())

    def test_wrong_date_pick_rejected_without_new_reference(self):
        self.seed()
        p = picks()
        for leg in p["tickets"][0]["legs"]:
            leg["kickoff_central"] = "2026-11-13 19:15"
        with self.assertRaisesRegex(ValueError, "no existing.*schedule"):
            si.execute(self.file(p), now=NOW)
        self.assertEqual(len(self.schedule()["games"]), 1)
        self.assertFalse((self.root / "intelligence/splash_picks_log.csv").exists())

    def test_legacy_csv_header_migration_retains_old_rows(self):
        import csv
        path = self.root / "old.csv"
        old = {"ticket_id": "old", "record_id": "r1", "locked_line": "6.5"}
        with path.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(old))
            writer.writeheader()
            writer.writerow(old)
        si.sc.append_log(path, [dict(old, ticket_id="new", model_status="unpriced",
                                     reference_origin="repository")])
        with path.open(newline="") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(None not in r for r in rows))
        self.assertEqual({k: rows[0][k] for k in old}, old)
        self.assertEqual(rows[1]["model_status"], "unpriced")


if __name__ == "__main__":
    unittest.main()
