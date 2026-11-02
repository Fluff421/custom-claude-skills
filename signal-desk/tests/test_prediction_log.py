import csv
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import prediction_log as pl  # noqa: E402

NOW = "2026-11-02T03:00:00+00:00"
GAMES = {"recA": {"ESPN Event ID": "401", "ESPN Pulled At": "2026-11-02T02:10:00.000Z"},
         "recB": {"ESPN Event ID": "402", "ESPN Pulled At": "2026-11-02T02:40:00.000Z"}}
LP = {"NCAAF": {"sigma_margin": 16.5, "sigma_total": 13.0, "k_margin": 0.162, "k_total": 0.3}}
AP = {"NCAAF": {"Sigma": 20, "Market Blend K": 0.162}}


def pick(**kw):
    r = {"pick_id": "spread:recA", "last_updated": NOW, "frozen": "", "league": "NCAAF", "market": "spread", "game_ids": "recA",
         "selection": "X -3", "side": "home", "line": "-3", "price": "-110", "prob": "0.52", "edge": "0.4", "edge_unit": "pts",
         "tier": "No Play", "units": "0"}
    r.update(kw)
    return r


class Build(unittest.TestCase):
    def test_provenance_fields(self):
        rows = pl.build_rows({"spread:recA": pick()}, NOW, GAMES, LP, AP, {})
        self.assertEqual(len(rows), 1)
        r = rows[0]
        for c in ("model_version", "config_hash", "data_cutoff_timestamp", "league", "sigma_version", "k_version",
                  "prediction_timestamp", "event_id"):
            self.assertTrue(r[c], c)
        self.assertEqual(r["event_definition"], "spread_cover")
        self.assertEqual(r["event_id"], "401")
        self.assertIn("airtable.Sigma=20", r["sigma_version"])
        self.assertIn("margin-blend", r["k_version"])

    def test_event_definitions_distinct(self):
        self.assertEqual(pl.EVENT_DEFINITION["moneyline"], "outright_win")
        self.assertEqual(pl.EVENT_DEFINITION["total"], "total_over_under")

    def test_unchanged_pick_not_relogged_and_frozen_skipped(self):
        first = pl.build_rows({"spread:recA": pick()}, NOW, GAMES, LP, AP, {})[0]
        later = "2026-11-02T06:00:00+00:00"
        self.assertEqual(pl.build_rows({"spread:recA": pick(last_updated=later)}, later, GAMES, LP, AP, {"spread:recA": first}), [])
        self.assertEqual(len(pl.build_rows({"spread:recA": pick(last_updated=later, prob="0.55")}, later, GAMES, LP, AP,
                                           {"spread:recA": first})), 1)
        self.assertEqual(pl.build_rows({"spread:recA": pick(frozen="1")}, NOW, GAMES, LP, AP, {}), [])

    def test_parlay_cutoff_is_latest_leg(self):
        r = pl.build_rows({"parlay:recA+recB": pick(pick_id="parlay:recA+recB", market="parlay", game_ids="recA+recB")},
                          NOW, GAMES, LP, AP, {})[0]
        self.assertEqual(r["data_cutoff_timestamp"], "2026-11-02T02:40:00.000Z")
        self.assertEqual(r["event_id"], "401+402")

    def test_append_only(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "predictions_log.csv")
            a = pl.build_rows({"spread:recA": pick()}, NOW, GAMES, LP, AP, {})
            pl.append(path, a)
            later = "2026-11-02T06:00:00+00:00"
            b = pl.build_rows({"spread:recA": pick(last_updated=later, prob="0.55")}, later, GAMES, LP, AP, pl.read_last(path))
            pl.append(path, b)
            rows = list(csv.DictReader(open(path, encoding="utf-8")))
            self.assertEqual([r["prob"] for r in rows], ["0.52", "0.55"])
            self.assertEqual(rows[0]["prediction_id"], a[0]["prediction_id"])


if __name__ == "__main__":
    unittest.main()
