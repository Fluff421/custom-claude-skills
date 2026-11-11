import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import line_source as ls  # noqa: E402

ESPN_NOTE = "3/14 | injuries: NFL auto | priced off ESPN line (no Splash line) | features:abc"


def row(grade, src="splash", tier="Lean", p=0.55, clv=None):
    f = {"Grade": grade, "Sharp-Sheet Tier": tier, "Sharp-Sheet Est. Win Prob %": p,
         "Sharp-Sheet Data Completeness": "3/14 | features:abc"}
    if src == "splash":
        f["Vegas Implied Home Margin"] = -3.0
    elif src == "espn":
        f["Sharp-Sheet Data Completeness"] = ESPN_NOTE
        f["Vegas Implied Home Margin"] = None
    if clv is not None:
        f["Sharp-Sheet CLV Points"] = clv
    return f


class SourceTests(unittest.TestCase):
    def test_classifies_each_source(self):
        self.assertEqual(ls.source(row("Win", "splash")), "splash")
        self.assertEqual(ls.source(row("Win", "espn")), "espn")
        self.assertEqual(ls.source(row("Win", "none")), "unknown")

    def test_espn_note_wins_even_if_a_line_is_present(self):
        f = row("Win", "espn")
        f["Vegas Implied Home Margin"] = -2.5
        self.assertEqual(ls.source(f), "espn")

    def test_repriced_pick_without_note_counts_as_splash(self):
        f = row("Win", "splash")
        f["Sharp-Sheet Data Completeness"] = "3/14 | features:abc"
        self.assertEqual(ls.source(f), "splash")


class ModeTests(unittest.TestCase):
    def test_default_is_all_and_keeps_every_row(self):
        fs = [row("Win", "splash"), row("Loss", "espn"), row("Win", "none")]
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(ls.learn_mode(), "all")
            self.assertEqual(ls.for_learning(fs), fs)
            self.assertEqual(ls.airtable_filter(), "")

    def test_splash_mode_keeps_only_splash_rows(self):
        fs = [row("Win", "splash"), row("Loss", "espn"), row("Win", "none")]
        out = ls.for_learning(fs, "splash")
        self.assertEqual(len(out), 1)
        self.assertEqual(ls.source(out[0]), "splash")
        flt = ls.airtable_filter("splash")
        self.assertIn("{Vegas Implied Home Margin}!=''", flt)
        self.assertIn("FIND('priced off ESPN line'", flt)

    def test_bad_mode_fails_loudly(self):
        with mock.patch.dict(os.environ, {"LEARN_LINE_SOURCE": "espn-only"}):
            with self.assertRaises(SystemExit):
                ls.learn_mode()


class CardTests(unittest.TestCase):
    def test_cards_are_separate_and_complete(self):
        fs = ([row("Win", "splash", clv=1.0)] * 4 + [row("Loss", "splash", clv=-0.5)] * 2
              + [row("Win", "espn", tier="No Play", p=0.52, clv=0.5)] * 3 + [row("Push", "espn")]
              + [row("Win", "none")])
        c = ls.report_cards(fs)
        self.assertEqual(c["unknown"], 1)
        s, e = c["splash"], c["espn"]
        self.assertEqual((s["wins"], s["losses"], s["pushes"]), (4, 2, 0))
        self.assertAlmostEqual(s["hit_rate"], 0.667)
        self.assertIn("brier", s)
        self.assertEqual(s["clv_n"], 6)
        self.assertAlmostEqual(s["clv_mean"], 0.5)
        self.assertEqual((e["wins"], e["losses"], e["pushes"]), (3, 0, 1))
        self.assertNotIn("brier", e)          # under 5 rows with a probability
        self.assertEqual(e["tiers"]["No Play"]["n"], 3)
        self.assertEqual(s["tiers"]["Lean"]["clv_n"], 6)

    def test_empty_card_and_summary(self):
        c = ls.report_cards([row("Win", "splash")])
        self.assertEqual(c["espn"]["n"], 0)
        lines = ls.summary_lines("NFL", c, "all")
        self.assertIn("live learning uses: all", lines[0])
        self.assertTrue(any("espn-line: no graded picks yet" in x for x in lines))

    def test_cards_never_mutate_rows(self):
        fs = [row("Win", "splash", clv=1.0), row("Loss", "espn", clv=-1.0)]
        before = [dict(f) for f in fs]
        ls.report_cards(fs)
        ls.for_learning(fs, "splash")
        self.assertEqual(fs, before)


if __name__ == "__main__":
    unittest.main()
