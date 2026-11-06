"""Timestamped conference-report snapshots; never substitute fetch-time freshness."""
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import html
import json
import re
from zoneinfo import ZoneInfo

ROOT = "https://kickoffstatus.com"


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
        entries, observed = [], 0
        for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>", table[1], re.S | re.I):
            cells = re.findall(r"<td\b[^>]*>(.*?)</td>", tr, re.S | re.I)
            if len(cells) < 3:
                raise ValueError(f"{path}: incomplete player row")
            player = text(re.sub(r'<span\b[^>]*class=["\']num["\'][^>]*>.*?</span>', "", cells[0], flags=re.S))
            pos, status = text(cells[1]), text(cells[2]).lower()
            status = {"gtd": "questionable", "game-time decision": "questionable"}.get(status, status)
            if not player or not pos or status not in ("out", "doubtful", "questionable", "probable", "available"):
                raise ValueError(f"{path}: unrecognized player/position/status")
            observed += 1
            if status != "available":
                entries.append({"player": player, "pos": pos, "status": status,
                                "injury": "", "date": stamp, "src": "K"})
        if not observed and not re.search(r"no players listed|no injuries reported", body, re.I):
            raise ValueError(f"{path}: empty table is not verified zero-injury coverage")
        teams[team] = entries
    if set(teams) != set(pair):
        raise ValueError(f"{path}: partial team coverage")
    return (date, *pair), teams, {"url": ROOT + path, "source_snapshot_at": stamp}


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
        return game_report(fetch(ROOT + path), path, now, key)
    with ThreadPoolExecutor(max_workers=2) as pool:
        reports = list(pool.map(read, paths))
    games = {}
    for identity, teams, meta in reports:
        if identity in games:
            raise ValueError(f"duplicate report for {identity}")
        games[identity] = (teams, meta)
    missing = expected - games.keys()
    if missing:
        raise ValueError(f"missing expected game coverage: {sorted(missing)}")
    teams, metadata = {}, []
    for identity in sorted(expected):
        observed, meta = games[identity]
        for team, entries in observed.items():
            if team in teams and teams[team] != entries:
                raise ValueError(f"conflicting reports for {team}")
            teams[team] = entries
        metadata.append(meta)
    return teams, stamp, {"provider": "Kickoff Status", "expected_games": len(expected),
                          "covered_games": len(expected), "reports": metadata}
