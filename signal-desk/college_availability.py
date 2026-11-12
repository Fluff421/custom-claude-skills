"""Timestamped conference-report snapshots; never substitute fetch-time freshness."""
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import html
import json
import re
from zoneinfo import ZoneInfo

ROOT = "https://kickoffstatus.com"

class CoverageError(ValueError):
    def __init__(self, coverage):
        self.coverage = coverage
        super().__init__(f"verified {coverage['covered_games']}/{coverage['expected_games']} games; "
                         + "; ".join(coverage["failures"]))


class PendingReport(ValueError):
    """The conference has not posted this game's report yet. The source's own expected posting time
    is kept so each game is labelled pending (not yet due) or overdue instead of failing the slate."""
    def __init__(self, path, identity, expected_at, overdue):
        self.identity, self.expected_at, self.overdue = identity, expected_at, overdue
        state = "overdue since" if overdue else "not yet due; expected"
        super().__init__(f"{path}: official availability report {state} {expected_at}")


PACIFIC = ZoneInfo("America/Los_Angeles")
INDEPENDENT = "none: independent program publishes no official report"
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def expected_report_time(page, kickoff):
    """Parse the source's notice ('Report expected: Thu 3:00 PM PT' or 'Usually posts game day
    ~7:30 AM PT') into an aware time. A weekday means the latest such day on or before the
    Pacific kickoff date; 'game day' means the Pacific kickoff date."""
    plain = re.sub(r"\s+", " ", text(re.sub(r"<(script|style)\b.*?</\1>", "", page, flags=re.S | re.I)))
    day = kickoff.astimezone(PACIFIC).date()
    match = re.search(r"Report expected:\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w*\s+(\d{1,2}:\d{2}\s*[AP]M)\s*P[SD]?T\b", plain, re.I)
    if match:
        day -= dt.timedelta(days=(day.weekday() - DAYS.index(match[1][:3].title())) % 7)
    else:
        match = re.search(r"Usually posts (game day) ~?\s*(\d{1,2}:\d{2}\s*[AP]M)\s*P[SD]?T\b", plain, re.I)
        if not match:
            return None
    clock = dt.datetime.strptime(match[2].replace(" ", "").upper(), "%I:%M%p").time()
    return dt.datetime.combine(day, clock, PACIFIC)


def text(value):
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def source_stamp(page, now):
    match = re.search(r'Data last refreshed\s*<time\b[^>]*datetime=["\']([^"\']+)', page, re.I)
    if not match:
        raise ValueError("missing published data-refresh timestamp")
    stamp = dt.datetime.fromisoformat(html.unescape(match[1]).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("source data-refresh timestamp has no timezone")
    age = (now - stamp).total_seconds() / 3600
    limit = 4 if now.astimezone(ZoneInfo("America/Chicago")).weekday() in (2, 3, 4, 5) else 26
    if age < -5 / 60 or age >= limit:
        raise ValueError(f"source data-refresh timestamp age {age:.2f}h outside 0..{limit}h")
    return match[1]


def game_report(page, path, now, key):
    stamp = source_stamp(page, now)
    events = []
    for raw in re.findall(r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', page, re.S | re.I):
        value = json.loads(raw)
        nodes = value if isinstance(value, list) else value.get("@graph", [value])
        events.extend(v for v in nodes if isinstance(v, dict) and v.get("@type") == "SportsEvent")
    if len(events) != 1:
        raise ValueError(f"{path}: missing unambiguous SportsEvent identity")
    event = events[0]
    kickoff = dt.datetime.fromisoformat(str(event.get("startDate", "")).replace("Z", "+00:00"))
    if kickoff.tzinfo is None:
        raise ValueError(f"{path}: event kickoff has no timezone")
    date = kickoff.astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat()
    if not re.match(rf"/games/{re.escape(date)}-", path):
        raise ValueError(f"{path}: report date does not match event identity")
    pair = (key(event["awayTeam"]["name"]), key(event["homeTeam"]["name"]))
    if not all(pair) or pair[0] == pair[1]:
        raise ValueError(f"{path}: invalid team identity")
    report_label = re.search(r'<p\b[^>]*class=["\']qa-asof["\'][^>]*>(.*?)</p>', page, re.S | re.I)
    if not report_label or not re.search(r"latest official report.*?posted", text(report_label[1]), re.I):
        expected_at = expected_report_time(page, kickoff)
        if expected_at is not None:
            raise PendingReport(path, (date, *pair), expected_at.isoformat(), now >= expected_at)
        plain = re.sub(r"\s+", " ", text(re.sub(r"<(script|style)\b.*?</\1>", "", page, flags=re.S | re.I)))
        if re.search(r"\bIndependent: no official report\b", plain):
            raise PendingReport(path, (date, *pair), INDEPENDENT, True)
        raise ValueError(f"{path}: official availability report not published")
    if '<div class="teams2">' not in page:
        raise ValueError(f"{path}: missing official team reports")
    official = page.split('<div class="teams2">', 1)[1]
    official = re.split(r'<section\b[^>]*class=["\'][^"\']*\bunofficial\b', official, flags=re.I)[0]
    teams = {}
    pattern = r'<h3\b[^>]*>\s*<a\b[^>]*href=["\']/teams/[^>]*>(.*?)</a>.*?</h3>(.*?)(?=<h3\b|$)'
    for name, body in re.findall(pattern, official, re.S | re.I):
        team = key(text(name))
        if team not in pair:
            continue
        table = re.search(r"<tbody\b[^>]*>(.*?)</tbody>", body, re.S | re.I)
        if not table:
            raise ValueError(f"{path}: missing structured table for {text(name)}")
        entries, observed, parsed = [], 0, []
        for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>", table[1], re.S | re.I):
            cells = re.findall(r"<td\b[^>]*>(.*?)</td>", tr, re.S | re.I)
            if len(cells) < 3:
                raise ValueError(f"{path}: incomplete player row")
            player = text(re.sub(r'<span\b[^>]*class=["\']num["\'][^>]*>.*?</span>', "", cells[0], flags=re.S))
            pos, status = text(cells[1]), text(cells[2]).lower()
            # Some official-table rows put the position in the player cell and
            # leave Pos blank. Use only an explicit football position prefix,
            # never a roster lookup or a guess from the player's name.
            if not pos:
                inline = re.fullmatch(
                    r"(QB|RB|WR|TE|OL|OT|OG|OC|C|G|T|DL|DT|DE|EDG|EDGE|"
                    r"LB|ILB|OLB|DB|CB|S|FS|SS|K|P|LS|FB|ATH)\s+(.+)", player)
                if inline:
                    pos, player = inline.groups()
            status = {"gtd": "questionable", "game-time decision": "questionable",
                      "not listed": "available"}.get(status, status)
            if not player or status not in ("out", "doubtful", "questionable", "probable", "available"):
                raise ValueError(f"{path}: unrecognized player/position/status: {player!r}/{pos!r}/{status!r}")
            parsed.append((player, pos, status))
        positions = {}
        for player, pos, _ in parsed:
            if pos:
                positions.setdefault(player.casefold(), set()).add(pos)
        seen = {}
        for player, pos, status in parsed:
            supplied = positions.get(player.casefold(), set())
            if len(supplied) > 1:
                raise ValueError(f"{path}: conflicting positions for {player!r}")
            if not pos and len(supplied) == 1:
                pos = next(iter(supplied))
            if not pos:
                raise ValueError(f"{path}: unrecognized player/position/status: {player!r}/{pos!r}/{status!r}")
            identity = (player.casefold(), pos)
            if identity in seen:
                if seen[identity] != status:
                    raise ValueError(f"{path}: conflicting statuses for {player!r}")
                continue
            seen[identity] = status
            observed += 1
            if status != "available":
                entries.append({"player": player, "pos": pos, "status": status,
                                "injury": "", "date": stamp, "src": "K"})
        if not observed and not re.search(r"no players listed|no injuries reported", body, re.I):
            raise ValueError(f"{path}: empty table is not verified zero-injury coverage")
        teams[team] = entries
    if set(teams) != set(pair):
        raise ValueError(f"{path}: partial team coverage")
    return (date, *pair), teams, {"url": ROOT + path, "source_snapshot_at": stamp,
                                "official_report_label": text(report_label[1])}


def load(rows, fetch, now, key):
    expected = set()
    for row in rows:
        f = row["fields"]
        date = str(f.get("Date", ""))[:10]
        dt.date.fromisoformat(date)
        expected.add((date, key(f.get("Away Team", "")), key(f.get("Home Team", ""))))
    index = fetch(ROOT + "/")
    stamp = source_stamp(index, now)
    indexed = {}
    for path, body in re.findall(r'<a\b[^>]*href=["\'](/games/\d{4}-\d{2}-\d{2}-[a-z0-9-]+/)["\'][^>]*>(.*?)</a>', index, re.S):
        names = re.findall(r'<span\b[^>]*class=["\']nm["\'][^>]*>(.*?)</span>', body, re.S)
        if len(names) != 2:
            continue
        identity = (path[7:17], *(key(text(name).lstrip("@ ")) for name in names))
        if identity in expected:
            if identity in indexed and indexed[identity] != path:
                raise ValueError(f"conflicting index reports for {identity}")
            indexed[identity] = path
    missing_index = expected - indexed.keys()
    if missing_index:
        raise ValueError(f"missing expected game coverage in source index: {sorted(missing_index)}")
    paths = sorted(set(indexed.values()))
    if not paths or len(paths) > 80:
        raise ValueError("missing or excessive current game-report links")
    def read(path):
        try:
            return game_report(fetch(ROOT + path), path, now, key)
        except PendingReport as exc:
            return exc
        except Exception as exc:
            return f"{path}: {exc}"
    with ThreadPoolExecutor(max_workers=2) as pool:
        reports = list(pool.map(read, paths))
    games, failures, pending = {}, [], {}
    for report in reports:
        if isinstance(report, PendingReport):
            if report.identity in expected:
                pending[report.identity] = (report.expected_at, report.overdue)
            else:
                failures.append(f"{report}: identity does not match the index")
            continue
        if isinstance(report, str):
            failures.append(report)
            continue
        identity, teams, meta = report
        if identity in games:
            raise ValueError(f"duplicate report for {identity}")
        games[identity] = (teams, meta)
    missing = expected - games.keys() - pending.keys()
    pending_rows = [[*identity, at, overdue] for identity, (at, overdue) in sorted(pending.items())]
    if missing:
        raise CoverageError({"provider": "Kickoff Status", "expected_games": len(expected),
                             "covered_games": len(expected & games.keys()), "pending_games": pending_rows,
                             "source_snapshot_at": stamp, "failures": failures,
                             "reports": [meta for _, meta in games.values()]})
    teams, metadata = {}, []
    for identity in sorted(expected & games.keys()):
        observed, meta = games[identity]
        for team, entries in observed.items():
            if team in teams and teams[team] != entries:
                raise ValueError(f"conflicting reports for {team}")
            teams[team] = entries
        metadata.append(meta)
    return teams, stamp, {"provider": "Kickoff Status", "expected_games": len(expected),
                          "covered_games": len(expected & games.keys()), "pending_games": pending_rows,
                          "reports": metadata}
