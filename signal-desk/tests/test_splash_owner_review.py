"""Synthetic owner-review cases. No owner dumps or invented observations."""
import copy
import hashlib
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from test_splash_import import GAME, NOW, lines, picks
import splash_import as si


class OwnerReview(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.patch = mock.patch.object(si, "HERE", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def source(self, d):
        raw = (json.dumps(d, indent=2) + "\n").encode()
        return raw, {
            "schema": "signal-desk.splash-review.v1",
            "date_code": d["date_code"],
            "input_sha256": hashlib.sha256(raw).hexdigest(),
            "warning_resolutions": [],
        }

    def save_review(self, review):
        path = self.root / "intelligence/splash_import/reviews" / (review["date_code"] + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(review))
        return path

    def test_without_review_raw_blockers_still_reject(self):
        d = lines()
        d["warnings"] = ["Status is not shown"]
        raw, _ = self.source(d)
        working, audit = si.reviewed_input(d, raw)
        self.assertEqual(working, d)
        self.assertIsNone(audit)
        with self.assertRaisesRegex(si.Rejected, "warnings"):
            si.plan(working, [GAME], [], [], NOW)

    def test_explicit_metadata_review_preserves_raw_and_observations(self):
        d = lines()
        d["game_count"] = {"NFL": 9}
        d["warnings"] = ["Status is not shown"]
        before = copy.deepcopy(d)
        raw, review = self.source(d)
        review["count_policy"] = "owner_confirms_complete_games_array"
        review["warning_resolutions"] = [{
            "warning": "Status is not shown",
            "resolution": "No status inference; the original owner-observed kickoff is retained.",
        }]
        self.save_review(review)
        working, audit = si.reviewed_input(d, raw)
        self.assertEqual(d, before)
        self.assertEqual(working["games"], before["games"])
        self.assertEqual(working["game_count"], {"NFL": 1})
        self.assertEqual(working["warnings"], [])
        self.assertEqual(audit["original_warnings"], before["warnings"])
        self.assertEqual(audit["original_game_count"], {"NFL": 9})
        self.assertEqual(si.plan(working, [GAME], [], [], NOW)["expected_rows"], 1)

    def test_review_requires_exact_checksum_and_date_code(self):
        for key, value in (("input_sha256", "0" * 64), ("date_code", "SPL-L-20261109-0000")):
            d = lines()
            raw, review = self.source(d)
            review[key] = value
            path = self.root / "intelligence/splash_import/reviews" / (d["date_code"] + ".json")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(review))
            with self.subTest(key=key), self.assertRaisesRegex(si.Rejected, "checksum|date_code"):
                si.reviewed_input(d, raw)

    def test_unknown_review_changes_and_blank_resolutions_reject(self):
        d = lines()
        raw, review = self.source(d)
        review["home_spread"] = 100
        self.save_review(review)
        with self.assertRaisesRegex(si.Rejected, "unsupported review"):
            si.reviewed_input(d, raw)
        del review["home_spread"]
        d["warnings"] = ["Status is not shown"]
        raw, review = self.source(d)
        review["warning_resolutions"] = [{"warning": "Status is not shown", "resolution": ""}]
        self.save_review(review)
        with self.assertRaisesRegex(si.Rejected, "resolution"):
            si.reviewed_input(d, raw)

    def test_unresolved_warning_still_blocks(self):
        d = lines()
        d["warnings"] = ["Status is not shown", "Orientation is uncertain"]
        raw, review = self.source(d)
        review["warning_resolutions"] = [{"warning": d["warnings"][0], "resolution": "Status remains unknown."}]
        self.save_review(review)
        working, _ = si.reviewed_input(d, raw)
        self.assertEqual(working["warnings"], ["Orientation is uncertain"])
        with self.assertRaisesRegex(si.Rejected, "warnings"):
            si.plan(working, [GAME], [], [], NOW)

    def test_review_does_not_waive_signed_spread_validation(self):
        d = lines()
        d["games"][0]["home_spread"] = 6.5
        raw, review = self.source(d)
        review["count_policy"] = "owner_confirms_complete_games_array"
        self.save_review(review)
        working, _ = si.reviewed_input(d, raw)
        with self.assertRaisesRegex(si.Rejected, "away_spread"):
            si.plan(working, [GAME], [], [], NOW)

    def test_completed_date_only_matches_existing_game_without_inventing_kickoff(self):
        d = picks()
        d["page_type"] = "completed"
        for leg in d["tickets"][0]["legs"]:
            leg["kickoff_central"] = None
        d["tickets"][0]["legs"][0]["selection"] = "Buccaneers"
        raw, review = self.source(d)
        review["completed_game_dates"] = [
            {"ticket_id": d["tickets"][0]["ticket_id"], "leg_index": i,
             "game_date_central": "2026-11-15"}
            for i in range(2)
        ]
        self.save_review(review)
        working, audit = si.reviewed_input(d, raw)
        self.assertTrue(all(leg["kickoff_central"] is None for leg in working["tickets"][0]["legs"]))
        result = si.plan(working, [GAME], [], [], NOW)
        self.assertEqual(result["expected_rows"], 2)
        self.assertIn("Tampa Bay Buccaneers +6.5", result["tickets"][0]["text"])
        self.assertEqual(len(audit["completed_game_dates"]), 2)
        self.assertNotIn("game_date_central", d["tickets"][0]["legs"][0])

    def test_date_only_is_not_allowed_for_pending_or_lines(self):
        for d in (picks(), lines()):
            legs = d["tickets"][0]["legs"] if "tickets" in d else d["games"]
            for leg in legs:
                leg["kickoff_central"] = None
                leg["game_date_central"] = "2026-11-15"
            with self.subTest(schema=d["schema"]), self.assertRaisesRegex(si.Rejected, "reliable Central"):
                si.plan(d, [GAME], [], [], NOW)

    def test_missing_date_and_ambiguous_or_reversed_completed_games_reject(self):
        d = picks()
        d["page_type"] = "completed"
        for leg in d["tickets"][0]["legs"]:
            leg["kickoff_central"] = None
        with self.assertRaisesRegex(si.Rejected, "game date"):
            si.plan(d, [GAME], [], [], NOW)
        for leg in d["tickets"][0]["legs"]:
            leg["game_date_central"] = "2026-11-15"
        for games, message in (
            ([GAME, dict(GAME, _id="r2")], "matches 2"),
            ([dict(GAME, **{"Home Team": GAME["Away Team"], "Away Team": GAME["Home Team"]})], "orientation"),
            ([], "matches 0"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(si.Rejected, message):
                si.plan(d, games, [], [], NOW)

    def test_missing_teased_line_still_rejects_after_date_review(self):
        d = picks()
        d["page_type"] = "completed"
        d["tickets"][0]["ticket_type"] = "teaser"
        for leg in d["tickets"][0]["legs"]:
            leg.update(kickoff_central=None, game_date_central="2026-11-15", teased_line=None)
        with self.assertRaisesRegex(si.Rejected, "teased_line"):
            si.plan(d, [GAME], [], [], NOW)

    def test_completed_review_cannot_inject_kickoffs_or_rewrite_existing_dates(self):
        d = picks()
        d["page_type"] = "completed"
        raw, review = self.source(d)
        review["completed_game_dates"] = [{
            "ticket_id": d["tickets"][0]["ticket_id"], "leg_index": 0,
            "game_date_central": "2026-11-16", "kickoff_central": "2026-11-16 12:00",
        }]
        self.save_review(review)
        with self.assertRaisesRegex(si.Rejected, "completed_game_dates"):
            si.reviewed_input(d, raw)

    def test_native_teaser_does_not_reconstruct_an_unobserved_base_line(self):
        d = picks()
        d["tickets"][0]["ticket_type"] = "teaser"
        for leg in d["tickets"][0]["legs"]:
            leg["teased_line"] = leg["line"]
            leg["base_line"] = None
        planned = si.plan(d, [GAME], [], [], NOW)
        with mock.patch.object(si.sc.mk, "project_game", side_effect=AssertionError("invented base")):
            rows, unmatched = si.sc.compare(
                [planned["tickets"][0]["ticket"]], [GAME],
                NOW.strftime("%Y-%m-%d %H:%MZ"), None, NOW.date())
        self.assertFalse(unmatched)
        self.assertTrue(all(r["base_line"] is None for r in rows))
        self.assertTrue(all(r.get("model_prob_lock", "") == "" for r in rows))
        self.assertTrue(all(r.get("movement_for_you", "") == "" for r in rows))

    def test_explicit_game_date_cannot_conflict_with_observed_kickoff(self):
        d = picks()
        d["tickets"][0]["legs"][0]["game_date_central"] = "2025-11-15"
        with self.assertRaisesRegex(si.Rejected, "conflicts"):
            si.plan(d, [GAME], [], [], NOW)
