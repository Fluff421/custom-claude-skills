import datetime as dt
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import seed_ledger as sl  # noqa: E402

TODAY = dt.date(2026, 11, 10)
END = TODAY + dt.timedelta(days=7)


def team(tid, location, display=None, short=None):
    return {"id": tid, "location": location, "displayName": display or f"{location} Mascots",
            "shortDisplayName": short or location, "name": "Mascots"}


def event(eid, home, away, date="2026-11-14T17:00Z", state="pre", neutral=False):
    return {"id": eid, "date": date, "status": {"type": {"state": state}},
            "competitions": [{"neutralSite": neutral, "competitors": [
                {"homeAway": "home", "team": home}, {"homeAway": "away", "team": away}]}]}


OSU, NW = team("194", "Ohio State"), team("77", "Northwestern")
BG, KENT = team("189", "Bowling Green"), team("2309", "Kent State")
FCS = team("9999", "Sacramento State")
FPI = {"194": 20.1, "77": -2.0, "189": -5.0, "2309": -12.0}


def ledger(game, home, away, date="2026-11-14", league="NCAAF", eid=None):
    f = {"League": league, "Date": date, "Game": game, "Home Team": home, "Away Team": away}
    if eid:
        f["ESPN Event ID"] = eid
    return {"id": "rec" + game, "fields": f}


class PlanTests(unittest.TestCase):
    def plan(self, events, rows=(), league="NCAAF", fpi=FPI):
        return sl.plan(league, events, fpi, list(rows), TODAY, END)

    def test_creates_only_the_six_structural_fields(self):
        creates, _ = self.plan([event("1", OSU, NW)])
        self.assertEqual(len(creates), 1)
        f = creates[0]["fields"]
        self.assertEqual(tuple(sorted(f)), tuple(sorted(sl.FIELDS)))
        self.assertEqual(f, {"Record Type": "Game", "League": "NCAAF", "Date": "2026-11-14",
                             "Game": "Northwestern @ Ohio State", "Home Team": "Ohio State",
                             "Away Team": "Northwestern"})

    def test_nfl_uses_full_display_name(self):
        bills = team("2", "Buffalo", "Buffalo Bills")
        jets = team("20", "New York", "New York Jets")
        creates, _ = self.plan([event("5", jets, bills)], league="NFL", fpi={"2": 5.0, "20": -3.0})
        self.assertEqual(creates[0]["fields"]["Game"], "Buffalo Bills @ New York Jets")

    def test_skips_game_already_in_ledger_by_teams(self):
        creates, rep = self.plan([event("1", OSU, NW)], [ledger("x", "Ohio State", "Northwestern", "2026-11-13")])
        self.assertEqual(creates, [])
        self.assertEqual(rep["existing"], 1)

    def test_skips_game_already_in_ledger_by_event_id(self):
        creates, rep = self.plan([event("1", OSU, NW)], [ledger("x", "Other", "Names", "2026-10-01", eid="1")])
        self.assertEqual((creates, rep["existing"]), ([], 1))

    def test_other_league_or_far_date_does_not_block(self):
        rows = [ledger("x", "Ohio State", "Northwestern", league="NFL"),
                ledger("y", "Ohio State", "Northwestern", date="2026-11-20")]
        creates, _ = self.plan([event("1", OSU, NW)], rows)
        self.assertEqual(len(creates), 1)

    def test_reversed_non_neutral_match_is_reported_not_created(self):
        creates, rep = self.plan([event("1", OSU, NW)], [ledger("x", "Northwestern", "Ohio State")])
        self.assertEqual(creates, [])
        self.assertEqual(len(rep["reversed"]), 1)

    def test_reversed_neutral_match_is_quietly_existing(self):
        creates, rep = self.plan([event("1", OSU, NW, neutral=True)], [ledger("x", "Northwestern", "Ohio State")])
        self.assertEqual((creates, rep["reversed"], rep["existing"]), ([], [], 1))

    def test_fcs_opponent_without_fpi_is_skipped_and_listed(self):
        creates, rep = self.plan([event("1", OSU, FCS)])
        self.assertEqual(creates, [])
        self.assertEqual(len(rep["no_fpi"]), 1)

    def test_started_or_final_games_are_never_created(self):
        creates, rep = self.plan([event("1", OSU, NW, state="in"), event("2", BG, KENT, state="post")])
        self.assertEqual((creates, rep["started"]), ([], 2))

    def test_window_uses_central_date_with_rollover(self):
        # 02:00 UTC Nov 18 is 20:00 CST Nov 17: inside the window, dated the 17th
        creates, _ = self.plan([event("1", OSU, NW, date="2026-11-18T02:00Z")])
        self.assertEqual(creates[0]["fields"]["Date"], "2026-11-17")
        # 06:00 UTC Nov 18 is Nov 18 Central: outside
        creates, rep = self.plan([event("2", BG, KENT, date="2026-11-18T06:00Z")])
        self.assertEqual((creates, rep["outside"]), ([], 1))

    def test_duplicate_events_in_one_run_create_once(self):
        creates, _ = self.plan([event("1", OSU, NW), event("1", OSU, NW), event("7", OSU, NW)])
        self.assertEqual(len(creates), 1)

    def test_alias_names_count_as_existing(self):
        ulm = team("2433", "UL Monroe", short="UL Monroe")
        la = team("309", "Louisiana")
        creates, _ = self.plan([event("1", ulm, la)], [ledger("x", "Louisiana-Monroe", "Louisiana")],
                               fpi={"2433": -15.0, "309": -4.0})
        self.assertEqual(creates, [])

    def test_caller_rows_are_not_mutated(self):
        rows = [ledger("x", "Bowling Green", "Kent State")]
        sl.plan("NCAAF", [event("1", OSU, NW)], FPI, rows, TODAY, END)
        self.assertEqual(len(rows), 1)

    def test_malformed_event_is_counted(self):
        _, rep = self.plan([{"id": "9", "date": "", "competitions": [{}]}])
        self.assertEqual(rep["bad"], 1)


class MainTests(unittest.TestCase):
    def run_main(self, env, n_events=3):
        evs = [event(str(i), team(str(100 + i), f"Home{i}"), team(str(200 + i), f"Away{i}")) for i in range(n_events)]
        fpi = {str(100 + i): 1.0 for i in range(n_events)} | {str(200 + i): 0.0 for i in range(n_events)}
        posted = []
        with mock.patch.dict(os.environ, {"AIRTABLE_TOKEN": "t", "AIRTABLE_BASE_ID": "appX", **env}, clear=True), \
                mock.patch.object(sl, "at_rows", return_value=[]), \
                mock.patch.object(sl.es, "load_fpi_index", side_effect=lambda lg, k: fpi if lg == "NCAAF" else {}), \
                mock.patch.object(sl, "fetch_events", return_value=evs), \
                mock.patch.object(sl.es, "http_get", side_effect=lambda *a: posted.append(a) or "{}"), \
                mock.patch.object(sl.dt, "datetime", wraps=dt.datetime) as fake_dt:
            fake_dt.now.return_value = dt.datetime(2026, 11, 10, 12, tzinfo=sl.CENTRAL)
            sl.main()
        return posted

    def test_dry_run_by_default_writes_nothing(self):
        self.assertEqual(self.run_main({}), [])

    def test_live_writes_in_batches_of_ten(self):
        posted = self.run_main({"SEED_LEDGER_LIVE": "1"}, n_events=23)
        self.assertEqual([len(p[3]["records"]) for p in posted], [10, 10, 3])
        self.assertTrue(all(p[2] == "POST" and p[3]["typecast"] for p in posted))

    def test_over_cap_aborts_without_writing(self):
        with self.assertRaises(SystemExit):
            self.run_main({"SEED_LEDGER_LIVE": "1", "SEED_MAX_CREATE": "2"})

    def test_missing_secrets_fail(self):
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(SystemExit):
            sl.main()


if __name__ == "__main__":
    unittest.main()
