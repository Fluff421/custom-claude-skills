from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import close_grade as cg


def event(eid, away, home, date="2026-11-11T00:00Z"):
    team = lambda loc, name: {"location": loc, "displayName": f"{loc} {name}", "shortDisplayName": loc, "name": name}
    return {"id": eid, "date": date, "competitions": [{"competitors": [
        {"homeAway": "home", "team": team(*home)}, {"homeAway": "away", "team": team(*away)}]}]}


def row(**fields):
    base = {"Date": "2026-11-10", "Home Team": "Miami (OH)", "Away Team": "Ohio"}
    return {"id": "recOrphan", "fields": {**base, **fields}}


EVENTS = [event("401866460", ("Ohio", "Bobcats"), ("Miami (OH)", "RedHawks")),
          event("401866459", ("Kent State", "Golden Flashes"), ("Bowling Green", "Falcons"))]


class ResolveEvent(unittest.TestCase):
    def by_event(self, events=EVENTS):
        return {e["id"]: e for e in events}

    def test_known_event_id_is_used_without_recovery(self):
        ev, recovered = cg.resolve_event(row(**{"ESPN Event ID": "401866460"}), self.by_event(), EVENTS)
        self.assertEqual((ev["id"], recovered), ("401866460", False))

    def test_known_event_id_absent_from_scoreboard_is_not_rematched(self):
        ev, recovered = cg.resolve_event(row(**{"ESPN Event ID": "999"}), self.by_event(), EVENTS)
        self.assertEqual((ev, recovered), (None, False))

    def test_missing_event_id_recovers_unique_team_and_central_date_match(self):
        # 00:00Z on Nov 11 is the evening of Nov 10 in Central time.
        ev, recovered = cg.resolve_event(row(), self.by_event(), EVENTS)
        self.assertEqual((ev["id"], recovered), ("401866460", True))

    def test_wrong_date_or_swapped_sides_do_not_match(self):
        self.assertEqual(cg.resolve_event(row(Date="2026-11-12"), self.by_event(), EVENTS), (None, False))
        swapped = row(**{"Home Team": "Ohio", "Away Team": "Miami (OH)"})
        self.assertEqual(cg.resolve_event(swapped, self.by_event(), EVENTS), (None, False))

    def test_ambiguous_matches_stay_unresolved(self):
        twice = EVENTS + [event("401866999", ("Ohio", "Bobcats"), ("Miami (OH)", "RedHawks"), "2026-11-10T23:00Z")]
        self.assertEqual(cg.resolve_event(row(), self.by_event(twice), twice), (None, False))

    def test_patches_for_one_record_are_merged(self):
        merged = cg.merge_patches([{"id": "a", "fields": {"ESPN Event ID": "1"}},
                                   {"id": "b", "fields": {"x": 1}},
                                   {"id": "a", "fields": {"Home Score": 34}}])
        self.assertEqual(merged, [{"id": "a", "fields": {"ESPN Event ID": "1", "Home Score": 34}},
                                  {"id": "b", "fields": {"x": 1}}])


if __name__ == "__main__":
    unittest.main()
