"""Synthetic submission admission/status/rollback tests; no network or owner data."""
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from test_splash_import import NOW
import splash_import as si
import splash_submission as ss


class SubmissionStatus(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.base = self.root / "intelligence/splash_import"
        self.source = self.base / "inbox/SPL-L-20261109-1916.json"
        self.source.parent.mkdir(parents=True)
        self.source.write_text('{"original":"unchanged"}\n')
        self.original = self.source.read_bytes()
        self.patch = mock.patch.object(si, "HERE", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def status(self):
        return json.loads((self.base / "status" / self.source.name).read_text())

    def test_admits_one_source_or_matching_review_pair(self):
        source = "signal-desk/intelligence/splash_import/inbox/" + self.source.name
        review = source.replace("/inbox/", "/reviews/")
        self.assertEqual(str(ss.admitted_paths([source])), source)
        self.assertEqual(str(ss.admitted_paths([review])), review)
        self.assertEqual(str(ss.admitted_paths([review, source])), source)
        for paths in ([], [source, source], [source, review.replace("1916", "1917")],
                      ["other/" + self.source.name], [source, review, "extra"]):
            with self.subTest(paths=paths), self.assertRaises(si.Rejected):
                ss.admitted_paths(paths)

    def test_rejection_restores_outputs_and_retains_original_and_review(self):
        review = self.base / "reviews" / self.source.name
        review.parent.mkdir(parents=True)
        review.write_text('{"owner":"review"}')
        old_log = self.root / "intelligence/splash_lines_log.csv"
        old_log.write_text("original log\n")

        def interrupted(*args, **kwargs):
            old_log.write_text("partially modified log\n")
            self.source.unlink()
            (self.base / "partial.json").write_text("{}")
            raise si.Rejected("signed spreads disagree")

        with mock.patch.object(si, "execute", side_effect=interrupted):
            self.assertEqual(ss.process(self.source, now=NOW), 1)
        self.assertEqual(old_log.read_text(), "original log\n")
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertTrue(review.exists())
        self.assertFalse((self.base / "partial.json").exists())
        self.assertEqual(self.status()["status"], "rejected")
        self.assertEqual(self.status()["accepted_rows"], 0)
        self.assertIn("signed spreads", self.status()["first_error"])

    def test_unexpected_failure_does_not_expose_exception_details(self):
        with mock.patch.object(si, "execute", side_effect=RuntimeError("secret-shaped diagnostic")):
            self.assertEqual(ss.process(self.source, now=NOW), 1)
        self.assertEqual(self.status()["status"], "failed")
        self.assertNotIn("secret-shaped", json.dumps(self.status()))

    def test_missing_original_does_not_recreate_it(self):
        self.source.unlink()
        review = self.base / "reviews" / self.source.name
        review.parent.mkdir(parents=True)
        review.write_text("{}")
        self.assertEqual(ss.process(review, now=NOW), 1)
        self.assertFalse(self.source.exists())
        self.assertEqual(self.status()["status"], "rejected")

    def test_status_does_not_call_a_missing_receipt_accepted(self):
        with mock.patch.object(si, "execute", return_value=None):
            self.assertEqual(ss.process(self.source, now=NOW), 1)
        self.assertEqual(self.status()["status"], "failed")
