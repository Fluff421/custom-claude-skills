# Data-source research — 2026-10-25

Owner ask: Grok researches sources. Claude changes code. This note does not change the model, Splash fields, or any sync script.

Checked: 2026-10-26 02:12 UTC (Sunday 2026-10-25, about 9:12pm CDT).
Repo SHA at check: `57a69ad0500fa34746fb490288c9b89d7bc88d28` (main).

No claim of betting accuracy. [signal-desk/LEDGER.md](../LEDGER.md) still says graded sample n=0, last updated 2026-10-24. I did not re-read Airtable.

## What I verified in the repo

These files and workflows exist on main. I read them. I did not run them.

| Piece | Where | Schedule in the YAML |
| --- | --- | --- |
| Phase 1 ESPN sync | `signal-desk/espn_sync.py`, `.github/workflows/espn-sync.yml` | `15 */3 * * *`. Live only if dispatch `live=true` or scheduled and `vars.ESPN_SYNC_LIVE == 'true'`. |
| Phase 2 close/grade | `signal-desk/close_grade.py`, `.github/workflows/close-grade.yml` | `12 * * * *`. Live gate: `vars.CLOSE_GRADE_LIVE`. |
| Phase 3 picks | `signal-desk/picks.py`, `.github/workflows/picks.yml` | `50 */3 * * *`. Live gate: `vars.PICKS_LIVE`. |
| Phase 3 context | `signal-desk/context_sync.py`, `.github/workflows/context-calibrate.yml` | Not re-quoted here. A dispatch on main succeeded 2026-10-26 01:21 UTC. |

Model on main, from [MODEL.md](../MODEL.md), dated 2026-10-24: `home_fpi - away_fpi + HFA`, NCAAF HFA 2.5, NFL HFA 2.0, neutral 0, watch at absolute edge 3.0. Do not retune these in the same PR as a new data source.

`espn_sync.py` writes NFL injury notes from `https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries` and explicitly skips NCAAF injuries. FPI still comes from scraping the HTML pages `espn.com/college-football/fpi` and `espn.com/nfl/fpi`.

### Airtable 403

ESPN Sync has 8 runs. None have `event=schedule`.

- Run 1, attempt 2, PR, failed. The sync step died in about one second (22:35:09Z to 22:35:10Z on 2026-10-25). That timing fits an immediate Airtable rejection. I did not download the log, so I cannot quote `INVALID_PERMISSIONS_OR_MODEL_NOT_FOUND` myself. https://github.com/Fluff421/custom-claude-skills/actions/runs/40238777848
- Run 2 succeeded after the commit that prefers `SIGNAL_DESK_BASE_ID`. https://github.com/Fluff421/custom-claude-skills/actions/runs/40242606121
- Main dispatch run 4 succeeded and the sync step took about 95 seconds (23:11:50Z to 23:13:25Z), which looks like a real pull rather than an instant 403. https://github.com/Fluff421/custom-claude-skills/actions/runs/40243640379
- The 00:15 UTC slot on 2026-10-26 had not produced a scheduled run by 02:12 UTC. GitHub cron can lag. Do not treat scheduled live mode as confirmed.

I did not inspect secret values. Rotating the previously pasted Airtable token is still an owner action.

## 1. NCAAF injuries — no league-wide feed

### ESPN is not usable. Verified this check.

`GET https://site.api.espn.com/apis/site/v2/sports/football/college-football/injuries`

- HTTP 200 at 2026-10-26 02:11 UTC. Body timestamp `2026-10-26T02:11:00Z`, season 2026 regular season.
- Only 3 teams, 1 row each, all old:
  - Florida, Kahleil Jackson, WR, Out, date `2020-11-21T18:31Z`
  - Rice, Braylen Walker, WR, Active, date `2022-11-26T22:30Z`
  - Virginia, Will Bettridge, PK, Active, date `2022-11-03T01:19Z`
- The Core API item behind Florida (`.../athletes/4693740/injuries/139830`) repeats that 2020 date and a comment about Vanderbilt. The athlete ref is a 2020 season URL.
- Team Site API `.../college-football/teams/57/injuries` and `.../teams/333/injuries` returned HTTP 200 and an empty JSON object.

Same endpoint for the NFL, same minute: HTTP 200, 32 teams, 800 rows (178 Out, 41 Questionable, 2 Doubtful, plus Active / IR / one suspension). NFL injuries in the current script are a real feed. NCAAF is not.

SportsDataverse `espn_cfb_injuries` is the same ESPN endpoint, saved as daily snapshots. The release page says last asset written **2026-10-01**, file `injuries_2026.parquet`. Stale as of this check, and it cannot be better than ESPN. https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/espn_cfb_injuries

### What actually exists: conference availability reports, conference games only

There is still no NCAA-wide report. I did not re-verify the old NCAA Board of Governors decision beyond a historical ESPN story. For 2026, conferences publish their own reports.

Verified:

- Big 12 official page is live. HTTP 200, title "Big 12 Football Player Availability Reporting". https://big12sports.com/sports/2025/8/14/FBreporting.aspx (the `2025/8/14` segment is the CMS slug; the page is the current reporting home). Policy PDF updated 2026-09-02: Wednesday/Thursday/Friday by 9:00pm CT for a Saturday game, game-day update 90 minutes before kickoff, statuses Out / Questionable / Probable / Out (1st Half) style categories. https://s3.amazonaws.com/big12sports.com/documents/2026/9/2/Updated_Player_Availability_Policy_9_2_2026.pdf
- Big Ten announced four reports per week on 2026-08-28, conference opponents only, published on BigTen.org. Midweek: Probable, Questionable, Doubtful, Out, Out (1st Half). Game day: Game Time Decision, Out, Out (1st Half). Unlisted means Available. https://bigten.org/news/2026/8/28/big-ten-announces-changes-to-football-availability-reporting-process.aspx (HTTP 200). I did not open this week's Big Ten HTML report.
- SEC practice, from beat reports dated 2026-10-22 through 2026-10-24, not from an SEC page I fetched: three days of updates plus a final report about 90 minutes before kickoff. Status words in those articles: Out, Doubtful, Questionable, Probable. I did not fetch secsports.com.

Kickoff Status (https://kickoffstatus.com/) is a useful index, not a source to write into Airtable.

- Homepage fetched HTTP 200. `<time datetime="2026-10-25T16:00:02-07:00">` — last updated Oct 25, 4:00 PM PT.
- It says it lists official reports for 10 conferences and separates a section literally labeled "Unofficial Injury Notes".
- At that timestamp the upcoming board was empty on purpose: "56 games listed across 10 conferences, 0 players on their reports" because next week's reports were not posted yet. Week 8 game-day changes were still in "Recently updated".
- The Big 12 subpage links to the official URL above. Only machine endpoint I saw was `/api/subscribe`. No injuries JSON.
- The page carries a betting-picks affiliate. Do not treat unofficial notes as availability.

Covers.com's college injury page is editorial, often "Undisclosed", and the rows I saw were dated Oct 17–19. Not an official report.

### Recommendation (one future PR, not this one)

Keep `Injury Notes` blank when no official report exists. Blank means "no report", not "healthy".

Until a parser exists, the owner can paste this one line per game. Same shape the NFL sync already writes:

```text
[SRC 2026-10-30 21:00Z] HOME: Pos Name STATUS; Pos Name STATUS | AWAY: none listed
```

Allowed STATUS values: `Out`, `Doubtful`, `Questionable`, `Probable`, `GTD`, `Out (1st Half)`. `SRC` is the conference and the report time, for example `Big12` or `SEC`. Do not copy Kickoff Status "Unofficial" lines into this field.

A later parser PR should read official conference HTML only, conference games only, and leave non-conference games blank. Do not add ESPN NCAAF injuries. Do not let that PR also change HFA, tiers, or Splash fields.

## 2. Second rating — and a better pipe for the same FPI

### ESPN FPI is already JSON. Verified this check. Same number the model uses, not a second opinion.

No API key. No HTML.

- NFL: `GET https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/2026/powerindex?limit=50`
  - HTTP 200, `count` 32. Item fields include `lastUpdated: 2026-10-25T06:00Z` and predictive `name: "fpi"` on a net-points scale ("expected point margin vs average opponent on neutral field"). Sample value 6.462, display 6.5. Team is only a `$ref`; the id is the last path segment (sample team id 25).
- NCAAF: same path with `leagues/college-football` and `limit=5`.
  - HTTP 200, `count` 138, so page with a higher limit (300) or follow pages. Sample team id 194, FPI 28.181, rank 1, `lastUpdated: 2026-10-25T08:00Z`.
  - That same item's `runDateTimeKey` was `20260926040051` (looks like 2026-09-26). I do not know why that key disagrees with `lastUpdated`. Log both. If `lastUpdated` is older than 3 days, leave FPI blank rather than guessing.

The scoreboard payload the sync already uses has ESPN team ids. Matching on id removes most of the alias table. Suggested Claude PR, by itself: read FPI from this endpoint, fall back to the HTML parser only if the JSON is empty, write the same `Home FPI` / `Away FPI` fields. Do not change HFA in that PR.

### Independent cross-check: CFBD SRS, then Elo. Not SP+.

CollegeFootballData docs fetched this check:

- SRS: https://api.collegefootballdata.com/srs-ratings.md — points versus an average FBS team on a neutral field, season-to-date, centered near 0. A rating of 8 is "roughly eight points better than average". Endpoint `GET /ratings/srs` (see https://api.collegefootballdata.com/api/ratings). Proprietary details (margin cap, home-field value) are not published.
- Elo: https://api.collegefootballdata.com/elo-ratings.md — sequential, not in points. `GET /ratings/elo` takes `year` and optional `week`. Do not drop an Elo gap into `model_home_margin`.
- SP+: `GET /ratings/sp`. Bill Connelly's model, published by ESPN. Useful as a second ESPN-family number. It is not an independence check on ESPN FPI.
- CFBD FPI (`GET /ratings/fpi`) is ESPN's FPI again. Use the powerindex URL above instead; it was free and current tonight.
- Game weather `GET /games/weather` is documented in the Python client as requiring Patreon, and the fields are game-time observations (good after the game, not a free pregame forecast). I did not call CFBD. No key in this environment. Free keys: https://collegefootballdata.com/key

Massey composite shows a 2026-10-25 column in search (https://masseyratings.com/ranks?s=cf&sym=cmp). A plain GET from this environment returned Cloudflare HTTP 403. Poor fit for a GitHub Action. I did not get a 200 from an independent NFL point rating tonight. Do not invent one.

Suggested later PR, after the JSON-FPI PR and only as logged columns: `Home SRS`, `Away SRS`, `SRS Pulled At`, from CFBD, new secret `CFBD_API_KEY`. Compare `srs_home - srs_away + HFA` to the FPI margin in the calibration log. Do not replace FPI, and do not change a tier cutoff, until there is a graded sample of dozens per the brief. SRS is season-to-date and not the same object as FPI.

## 3. Weather — log it, do not price it yet

ESPN scoreboard venue has `id`, `fullName`, `address`, `indoor`. No latitude or longitude. Verified on the NFL scoreboard (HTTP 200, 14 events) and the NCAAF scoreboard for 20261031 groups=80 (HTTP 200, 40 events).

Examples at check time:

- Lumen Field, venue id `3673`, Seattle, `indoor: false` (Chiefs at Seahawks, 2026-10-26 00:20Z).
- Mercedes-Benz Stadium, Atlanta, `indoor: true`.
- Stade de France, Saint-Denis, France, `indoor: false`. No US grid for that game.
- Gillette Stadium, Foxborough, Notre Dame vs Navy, `neutralSite: true`, `indoor: false`.

`indoor: true` is not "roof closed". Mercedes-Benz is retractable. A third-party NFL weather page said the Atlanta roof was open today; I did not verify the roof. Keep a small override list for retractable venues. Do not zero the forecast from the ESPN flag alone on those venues.

Pregame forecast, verified:

- Open-Meteo, no key: `https://api.open-meteo.com/v1/forecast` for 47.5952, -122.3316 (Lumen Field). Hour `2026-10-25T17:00` America/Los_Angeles: 55.1 F, precipitation probability 8, wind 1.3 mph, gust 6.7 mph. Terms page https://open-meteo.com/en/terms : free API is non-commercial, under 10,000 calls/day, 5,000/hour, 600/minute. A private ledger is plausibly inside that, but confirm before a commercial use. The free API has no SLA.
- NWS, no key, US only: `https://api.weather.gov/points/47.5952,-122.3316` HTTP 200 with a descriptive User-Agent. Grid `SEW 125,67`, hourly forecast URL returned, city Seattle. Send a User-Agent or NWS rejects the call. Does not cover Saint-Denis.

CFBD `/games/weather` is the wrong tool for the pregame job (Patreon, and it is kickoff observation). It is a reasonable post-game check once the slate is graded.

Suggested later PR, log only, new fields, not Splash and not the margin formula:

- `Weather Temp F`, `Weather Wind Mph`, `Weather Gust Mph`, `Weather Precip Pct`, `Weather Source`, `Weather Pulled At`
- Source string example: `Open-Meteo 2026-10-25T17:00-07:00`
- Join on ESPN venue id via a checked-in coordinate table. Domes with a fixed roof can store precip 0. Retractable roofs stay forecasted until the roof call is known.
- Add weather to the model only after a measured CLV difference on a real graded sample. [MODEL.md](../MODEL.md) already says no unit plays until a week is graded.

## 4. News — human digest only

ESPN news JSON is current and unstructured. Verified:

- `https://site.api.espn.com/apis/site/v2/sports/football/college-football/news?limit=3` — headlines at `2026-10-26T00:49:02Z` and `2026-10-25T23:33:23Z` (recruiting and a fine, not injuries).
- NFL news limit 2 — headlines at `2026-10-26T01:49:45Z` and `2026-10-26T01:33:50Z` (records and highlights).

Do not parse these into Injury Notes or into the margin.

## Suggested order for Claude, one PR each

1. FPI from the Core powerindex URL, matched on ESPN team id. Keep HTML as fallback. No HFA change.
2. Official-conference availability parser, or until then the manual line above. Never ESPN NCAAF injuries.
3. Log CFBD SRS beside FPI. New secret. No change to `model_home_margin`.
4. Log Open-Meteo / NWS weather beside the game. No change to `model_home_margin`.
5. Monitoring note: alert when an ESPN Sync run is missing its `schedule` event, when FPI `lastUpdated` is older than 3 days, and when a team id does not match. The 00:15 UTC gap on 2026-10-26 is the first item to explain.

## Assumed, not verified

- The one-second failure on run 1 is the 403 from the collaboration brief. Timing matches. Log text was not opened.
- SEC report cadence, beyond the 2026-10-22 to 2026-10-24 beat articles.
- Whether `runDateTimeKey` 20260926 means the NCAAF FPI value is older than `lastUpdated`.
- Phase 2 and Phase 3 grade the right fields. The files and successful workflow conclusions exist. [LEDGER.md](../LEDGER.md) still says n=0, and I did not grade a game.
- Open-Meteo non-commercial terms apply to this private workflow. The terms page says non-commercial. Nobody from Open-Meteo confirmed that reading.
