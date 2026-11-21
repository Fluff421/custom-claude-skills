#!/usr/bin/env python3
"""Parse the official NFL.com injury report into one CSV per team plus a manifest.

Read-only fetch of https://www.nfl.com/injuries/. Writes only under the output
directory given on the command line. A team section that says "No Injuries
Reported" gets a single row with report_status=no_injuries_reported. A blank
Injuries column never means healthy: every listed player keeps a practice status.
"""
import csv, datetime as dt, html, os, re, sys, urllib.request

URL = "https://www.nfl.com/injuries/"
COLS = ["league", "game", "team", "player", "status", "source_url", "retrieved_at_utc",
        "verified_or_assumed", "espn_event_id", "report_type", "report_status", "position", "notes"]


def clean(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def parse(page):
    # matchup strips: two team links each; sub-title spans name the team of the next table
    games, tokens = [], []
    for m in re.finditer(r'nfl-c-matchup-strip__team-fullname" href="/teams/([a-z0-9-]+)/"|'
                         r'd3-o-section-sub-title"><span>([^<]+)</span>|'
                         r'<table.*?</table>|nfl-o-no-results__text">([^<]+)<', page, re.S):
        tokens.append(m)
    slugs, pending, cur_game, out = [], None, None, []
    for m in tokens:
        if m.group(1):
            slugs.append(m.group(1))
            if len(slugs) == 2:
                cur_game = tuple(slugs)
                slugs = []
        elif m.group(2):
            pending = clean(m.group(2))
        elif m.group(3):
            out.append((cur_game, pending, None, clean(m.group(3))))
        else:
            rows = []
            for tr in re.findall(r"<tr>(.*?)</tr>", m.group(0), re.S):
                tds = [clean(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
                if len(tds) == 5:
                    rows.append(tds)
            out.append((cur_game, pending, rows, None))
    return out


def title(slug):
    return " ".join(w.capitalize() for w in slug.split("-"))


def main(outdir):
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    page = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    os.makedirs(outdir, exist_ok=True)
    manifest = []
    for game, short, rows, noinj in parse(page):
        away, home = game
        away_n, home_n = title(away), title(home)
        team_n = next((n for n in (away_n, home_n) if n.split()[-1] == short.split()[-1]), short)
        matchup = f"{away_n} at {home_n}"
        slug = away if team_n == away_n else home
        path = os.path.join(outdir, f"{slug}.csv")
        with open(path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(COLS)
            if noinj:
                w.writerow(["NFL", matchup, team_n, "", "", URL, now, "verified", "", "injury_report",
                            "no_injuries_reported", "", noinj])
                n = 1
            else:
                for player, pos, inj, practice, game_status in rows:
                    w.writerow(["NFL", matchup, team_n, player, game_status or practice, URL, now, "verified",
                                "", "injury_report", "published", pos,
                                "; ".join(x for x in (inj, f"practice={practice}") if x)])
                n = len(rows)
        manifest.append([team_n, matchup, f"{slug}.csv", n, "no_injuries_reported" if noinj else "published"])
    with open(os.path.join(outdir, "_manifest.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["team", "game", "file", "data_rows", "report_status"])
        w.writerows(manifest)
    print(f"retrieved_at_utc={now} teams={len(manifest)} rows={sum(r[3] for r in manifest)}")


if __name__ == "__main__":
    main(sys.argv[1])
