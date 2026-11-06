from pathlib import Path
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import injury_pull as ip
import producer_health as ph

FIXTURES = Path(__file__).parent / "fixtures"


class DraftEdgeContracts(unittest.TestCase):
    def test_current_team_cards_parse_without_inventing_update_time(self):
        page = (FIXTURES / "draftedge_cards.html").read_text(encoding="utf-8")
        teams, stamp = ip.parse_draftedge(page, ["SMU", "Virginia Tech"])
        self.assertEqual(stamp, "")
        self.assertEqual(sum(map(len, teams.values())), 2)
        self.assertEqual(teams["SMU"], [{"player": "Dramekco Green", "pos": "RB", "status": "out",
                                        "injury": "Hand", "date": "", "src": "D"}])
        self.assertEqual(teams["Virginia Tech"][0]["status"], "questionable")
        self.assertEqual(teams["Virginia Tech"][0]["injury"], "")

    def test_legacy_table_and_explicit_source_timestamp_still_parse(self):
        page = '''<span class="updated-time">October 30, 2026 11:56 AM</span>
        <tr data-status="out"><td>A Player</td><td>QB</td><td>SMU Mustangs</td>
        <td>Out</td><td>Foot</td></tr>'''
        teams, stamp = ip.parse_draftedge(page, ["SMU"])
        self.assertEqual(stamp, "October 30, 2026 11:56 AM")
        self.assertEqual(teams["SMU"][0]["injury"], "Foot")

    def test_empty_or_unrecognized_html_is_not_coverage(self):
        for page in ("", "<html>Access denied</html>", "<article data-status='out'>No team or player</article>"):
            self.assertEqual(ip.parse_draftedge(page, ["SMU"]), ({}, ""))

    def run_injury_command(self, rows, replacement=False, transform=None, live=False, extra_index="", source_names=None):
        page = (FIXTURES / "draftedge_cards.html").read_text(encoding="utf-8")
        covers = "".join(f'<a id="{i}"></a><section><div class="covers-CoversMatchups-teamName">'
                         f'{team}<br>Mascot</div></section>' for i, team in enumerate(("SMU", "Virginia Tech")))
        date = (ip.dt.datetime.now(ip.dt.timezone.utc).date() + ip.dt.timedelta(days=1)).isoformat()
        stamp = (ip.dt.datetime.now(ip.dt.timezone.utc) - ip.dt.timedelta(minutes=10)).isoformat()
        report = (FIXTURES / "kickoff_status_game.html").read_text().replace("%DATE%", date).replace("%STAMP%", stamp)
        if transform:
            report = transform(report)
        index = (f'<a class="card game" href="/games/{date}-virginia-tech-at-smu/">'
                 '<span class="nm">Virginia Tech</span><span class="nm">@ SMU</span></a>'
                 + extra_index +
                 f'Data last refreshed <time datetime="{stamp}">Refresh</time>')
        if source_names:
            for old, new in zip(("Virginia Tech", "SMU"), source_names):
                report, index = report.replace(old, new), index.replace(old, new)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = {"AIRTABLE_TOKEN": "fixture-token", "AIRTABLE_BASE_ID": "fixture-base", "INJURY_PULL_LIVE": "1" if live else "0",
                   "INJURY_SNAPSHOT_PATH": str(root / "snapshot.json")}
            with (patch.dict(os.environ, env, clear=True), patch.object(ph, "DATA", root),
                  patch.object(ip, "MIN_COVERS_TEAMS", 2), patch.object(ip, "MIN_DRAFTEDGE_ENTRIES", 2),
                  patch.object(ip, "fetch", side_effect=lambda url: covers if url == ip.COVERS_URL else page),
                  patch.object(ip, "fetch_kickoff", create=True,
                               side_effect=[index, report] if replacement else RuntimeError("fixture replacement unavailable")),
                  patch.object(ip.es, "at_list", return_value=rows), patch.object(ip.es, "at_patch") as writes,
                  redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO())):
                code = 0
                try:
                    ip.main()
                except SystemExit as exc:
                    code = exc.code
                if not live:
                    writes.assert_not_called()
                self.written = writes.call_args.args[-1] if writes.called else []
            health = json.loads((root / "producer_health/injury_pull.json").read_text())
            snapshot = json.loads((root / "snapshot.json").read_text())
            return code, health, snapshot

    def test_timestamped_complete_replacement_restores_health(self):
        date = (ip.dt.datetime.now(ip.dt.timezone.utc).date() + ip.dt.timedelta(days=1)).isoformat()
        code, health, snapshot = self.run_injury_command([{"id": "fixture", "fields": {
            "League": "NCAAF", "Date": date, "Grade": "Pending",
            "Home Team": "SMU", "Away Team": "Virginia Tech"}}], replacement=True)
        self.assertEqual(code, 0)
        self.assertEqual(health["status"], "ok")
        self.assertEqual(snapshot["secondary_provider"], "Kickoff Status")
        self.assertIn("Alex Example", str(snapshot["secondary"]))
        self.assertNotIn("Rumored Player", str(snapshot["secondary"]))
        self.assertNotIn("Available Example", str(snapshot["secondary"]))

    def future_row(self, **fields):
        date = (ip.dt.datetime.now(ip.dt.timezone.utc).date() + ip.dt.timedelta(days=1)).isoformat()
        return {"id": "fixture", "fields": {"League": "NCAAF", "Date": date, "Grade": "Pending",
                "Home Team": "SMU", "Away Team": "Virginia Tech", **fields}}

    def test_replacement_cannot_hide_missing_partial_or_unknown_reports(self):
        transforms = [
            lambda page: page.replace("Data last refreshed", "Not a source timestamp"),
            lambda page: page.replace('href="/teams/smu/"', 'href="/ignored/"'),
            lambda page: page.replace(">Questionable</span>", ">Maybe</span>"),
            lambda page: page.replace('startDate":"', 'startDate":"2001-01-01'),
            lambda page: page.replace("latest official report posted", "No report yet"),
            lambda page: page.replace("<td>QB</td>", "<td></td>"),
        ]
        for transform in transforms:
            with self.subTest(transform=transform):
                code, health, snapshot = self.run_injury_command([self.future_row()], replacement=True, transform=transform)
                self.assertEqual(code, 1)
                self.assertEqual(health["status"], "degraded")
                self.assertFalse(snapshot["sources"]["kickoff_status"])
                self.assertEqual(snapshot["replacement"]["expected_games"], 1)
                self.assertEqual(snapshot["replacement"]["covered_games"], 0)

    def test_stale_source_timestamp_is_not_replaced_with_fetch_time(self):
        old = (ip.dt.datetime.now(ip.dt.timezone.utc) - ip.dt.timedelta(days=2)).isoformat()
        import re
        code, health, _ = self.run_injury_command([self.future_row()], replacement=True,
            transform=lambda page: re.sub(r'datetime="[^"]+"', f'datetime="{old}"', page))
        self.assertEqual(code, 1)
        self.assertIn("timestamp age", str(health["errors"]))

    def test_one_covered_game_cannot_hide_another_missing_game(self):
        missing = self.future_row(**{"Home Team": "Uncovered School"})
        missing["id"] = "missing"
        code, health, _ = self.run_injury_command([self.future_row(), missing], replacement=True)
        self.assertEqual(code, 1)
        self.assertIn("missing expected game coverage", str(health["errors"]))

    def test_unrelated_nonledger_game_does_not_require_an_extra_fetch(self):
        date = self.future_row()["fields"]["Date"]
        unrelated = (f'<a class="card game" href="/games/{date}-other-at-unrelated/">'
                     '<span class="nm">Other</span><span class="nm">@ Unrelated</span></a>')
        code, _, _ = self.run_injury_command([self.future_row()], replacement=True, extra_index=unrelated)
        self.assertEqual(code, 0)

    def test_published_school_aliases_match_without_fuzzy_team_substitution(self):
        code, _, snapshot = self.run_injury_command([self.future_row(
            **{"Away Team": "Louisiana-Monroe", "Home Team": "Florida International"})],
            replacement=True, source_names=("UL Monroe", "FIU"))
        self.assertEqual(code, 0)
        self.assertEqual(snapshot["replacement"]["covered_games"], 1)

    def test_publisher_defined_not_listed_status_is_available_not_an_injury(self):
        code, _, snapshot = self.run_injury_command([self.future_row()], replacement=True,
            transform=lambda page: page.replace(">Available</td>", ">Not listed</td>"))
        self.assertEqual(code, 0)
        self.assertNotIn("Available Example", str(snapshot["secondary"]))

    def test_utc_event_crossing_midnight_matches_pacific_schedule_date(self):
        row = self.future_row()
        date = row["fields"]["Date"]
        following = (ip.dt.date.fromisoformat(date) + ip.dt.timedelta(days=1)).isoformat()
        code, _, _ = self.run_injury_command([row], replacement=True,
            transform=lambda page: page.replace(f"{date}T19:00:00-06:00", f"{following}T02:00:00Z"))
        self.assertEqual(code, 0)

    def test_all_available_is_verified_zero_not_an_empty_feed(self):
        code, health, snapshot = self.run_injury_command([self.future_row()], replacement=True,
            transform=lambda page: page.replace(">Out</span>", ">Available</span>").replace(">Questionable</span>", ">Available</span>"))
        self.assertEqual(code, 0)
        self.assertEqual(health["status"], "ok")
        self.assertEqual(sum(map(len, snapshot["secondary"].values())), 0)

    def test_live_update_preserves_manual_notes_and_graded_games(self):
        manual = self.future_row(**{"Injury Notes": "Owner verified; do not replace"})
        manual["id"] = "manual"
        graded = self.future_row(Grade="Win", **{"Home Team": "Historical school"})
        graded["id"] = "graded"
        code, _, snapshot = self.run_injury_command([self.future_row(), manual, graded], replacement=True, live=True)
        self.assertEqual(code, 0)
        self.assertEqual(snapshot["expected_rows"], 2)
        self.assertEqual([w["id"] for w in self.written], ["fixture"])
        self.assertEqual(set(self.written[0]["fields"]), {"Injury Notes"})

    def test_complete_names_with_same_initial_are_not_merged(self):
        extra = '<tr><td>Avery Example</td><td>OL</td><td>Out</td><td>Out</td></tr>'
        code, _, _ = self.run_injury_command([self.future_row()], replacement=True, live=True,
            transform=lambda page: page.replace("</tbody>", extra + "</tbody>", 1))
        self.assertEqual(code, 0)
        note = self.written[0]["fields"]["Injury Notes"]
        self.assertIn("Alex Example QB OUT", note)
        self.assertIn("Avery Example OL OUT", note)

    def test_missing_source_timestamp_still_fails_after_card_parser_is_fixed(self):
        rows = [{"id": "fixture", "fields": {"League": "NCAAF", "Home Team": "SMU",
                                           "Away Team": "Virginia Tech", "Game": "Fixture game"}}]
        code, health, snapshot = self.run_injury_command(rows)
        self.assertEqual(code, 1)
        self.assertEqual(health["status"], "degraded")
        self.assertIn("source updated-at", health["errors"][0])
        self.assertEqual(sum(map(len, snapshot["draftedge"].values())), 2)
        self.assertEqual(snapshot["draftedge_updated"], "")

    def test_no_upcoming_games_is_not_a_feed_dropout(self):
        code, health, _ = self.run_injury_command([])
        self.assertEqual(code, 0)
        self.assertEqual(health["status"], "no_games")
