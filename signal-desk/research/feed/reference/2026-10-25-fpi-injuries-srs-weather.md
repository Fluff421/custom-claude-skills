# Source audit — 2026-10-25 evening

Research only. This note does not change sync code, model files, or Splash fields.

Checked from this environment on 2026-10-26 02:43–02:48 UTC (Sunday 2026-10-25, about 9:43–9:48pm CDT). Base commit: `57a69ad0500fa34746fb490288c9b89d7bc88d28`.

Graded sample is n=0. No tuning claim. I did not re-read Airtable.

Every URL below was requested by me in that window unless I say otherwise. HTTP Date headers are the server clock on the response.

## 1. ESPN Core power index — FPI JSON

### Endpoints I called

No API key. Accept `application/json`. User-Agent `SignalDeskResearch/1.0`.

- `GET https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/2026/powerindex?limit=50`
  - HTTP 200, Date `Mon, 26 Oct 2026 02:43:40 GMT`, 310580 bytes, `count` 32.
- `GET https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/seasons/2026/powerindex?limit=100`
  - HTTP 200, same minute, `count` 138, `pageCount` 2, `pageSize` 100, 100 items.
- Same URL with `&page=2`
  - HTTP 200, Date `Mon, 26 Oct 2026 02:43:54 GMT`, 38 items.
- `GET https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/seasons/2026/powerindex/194`
  - HTTP 200, Date `Mon, 26 Oct 2026 02:45:19 GMT`. Full object. `predictives` is inline.

I did not re-fetch `https://www.espn.com/college-football/fpi` or the NFL HTML page in this pass.

### Object shape

Each item has keys: `team`, `season`, `lastUpdated`, `runDateTimeKey`, `predictives`, `efficiencies`.

`team` is only a `$ref`. The id is the path segment after `/teams/` and before `?`.

Example NFL ref: `http://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/2026/teams/25?lang=en&region=us` means id `25`. Direct team GET at 02:44:28 GMT returned San Francisco 49ers, abbreviation SF.

The FPI number is the predictive whose `name` is `fpi`.

- `value` is the full float. Ohio State id `194`: `28.181`, display `28.2`.
- `displayValue` is the one-decimal string.
- Description received: "Football Power Index that measures team's true strength on net points scale; expected point margin vs average opponent on neutral field."

`efficiencies` are 0–100 (`offefficiency`, `defefficiency`). They are not points. Do not write them into `Home FPI` or `Away FPI`.

This endpoint does not include home-field advantage. Keep the existing neutral-site HFA rule. Do not change HFA in the parser PR.

### The September key is stale. The ratings are not.

NFL, all 32 items:

- `lastUpdated`: `2026-10-25T06:00Z`
- `runDateTimeKey`: `20261025020004` (same night as `lastUpdated`)
- `season`: 2026
- FPI `value` range I computed: -7.613 to 6.462

NCAAF, all 138 items on both pages:

- `lastUpdated`: `2026-10-25T08:00Z` on every row
- `runDateTimeKey`: `20260926040051` on every row
- `season`: 2026

`20260926040051` reads as 2026-09-26 04:00:51. It did not move when `lastUpdated` did. For NCAAF it is a stale batch id, not the age of the rating.

Evidence the values are post-week-8, not a Sept 26 freeze:

1. `lastUpdated` is 2026-10-25 on every row.
2. Miami id `2390` in the power index: FPI `value` 27.539, display `27.5`, rank 3, wins 7, losses 0. Separately, `GET https://site.api.espn.com/apis/site/v2/sports/football/college-football/teams/2390` at Date `Mon, 26 Oct 2026 02:48:51 GMT` returned overall wins 7, losses 0, games played 7, standing summary "1st in ACC".
3. Display values match `signal-desk/data/fpi_2026-10-25.csv`, whose columns say source `https://www.espn.com/college-football/fpi`, `as_of_date` 2026-10-25, note `post-week-8`. I downloaded that file from raw GitHub at 02:44:27 GMT. I did not open the HTML page itself.

Name joins against that CSV using `displayValue` and rank:

- Direct lookups matched: Ohio State 28.2 rank 1, Notre Dame 27.7 rank 2, Miami 27.5 rank 3, Georgia 26.5 rank 4, Alabama 24.5 rank 5, Indiana 24.1 rank 6, LSU 24.0 rank 7, Texas 24.0 rank 8, New Mexico 7.9 rank 41, Duke 7.6 rank 42, Navy -6.3 rank 92, UTEP -24.2 rank 136, UL Monroe -25.3 rank 137, Sacramento State -33.2 rank 138.
- 103 further rows matched on an exact location or short-name key.
- Only disagreement: App State (id `2026`) and Georgia State (id `2247`) both have `value` -7.493 and display `-7.5`. JSON ranks are 96 and 95. The CSV swaps those two ranks. Nevada (id `2440`) is -7.484, rank 94.

I did not finish a 138-row name crosswalk. `GET https://site.api.espn.com/apis/site/v2/sports/football/college-football/teams?limit=400&groups=80` (HTTP 200, 02:44:50 GMT, 400 team objects) omitted ids that are in the power index, including Miami `2390`. Do not join through that list.

### Scoreboard id map

Scoreboard `competitors[].team.id` is the same id as the power-index `$ref`.

NFL scoreboard `GET https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?limit=20`, HTTP 200, Date `Mon, 26 Oct 2026 02:44:28 GMT`:

- Event `401873022`, Kansas City Chiefs at Seattle Seahawks, `2026-10-26T00:20Z`.
- Home id `26` Seattle Seahawks. Power index FPI `value` 3.382, display `3.4`, rank 6, wins 3, losses 3. `lastUpdated` `2026-10-25T06:00Z`.
- Away id `12` Kansas City Chiefs. Power index FPI `value` 5.159, display `5.2`, rank 2, wins 5, losses 0. Same `lastUpdated`.

NCAAF scoreboard `GET https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?dates=20261031&limit=5&groups=80`, HTTP 200, same minute:

- Event `401859185`, Notre Dame at Navy, `2026-10-31T16:00Z`, `neutralSite` true.
- Away id `87` Notre Dame. FPI `value` 27.73, display `27.7`, rank 2.
- Home id `2426` Navy. FPI `value` -6.282, display `-6.3`, rank 92, wins 2, losses 5.
- Both `lastUpdated` `2026-10-25T08:00Z`. Both `runDateTimeKey` `20260926040051`.

### Mapping spec

One code change later: read this JSON instead of scraping HTML. Do not change HFA, tiers, or Splash fields in that PR.

1. Collect string team ids from `competitions[].competitors[].team.id`.
2. GET the league power index. NFL: `limit=50` covered `count` 32. NCAAF: `limit=100` plus `page=2` until items equal `count`. If `count` is not 32 (NFL) or 138 (NCAAF), warn and do not guess missing teams.
3. Index:

```text
team_id = segment of team.$ref after "/teams/" and before "?"
fpi_value = predictives entry with name == "fpi", field value (float)
fpi_display = that entry's displayValue
fpi_updated = item.lastUpdated
fpi_run_key = item.runDateTimeKey
```

4. Set `Home FPI` and `Away FPI` from the home and away scoreboard ids. Compare ids as strings. If either id is missing, leave both fields unchanged and warn. No alias map and no prefix match. A prefix match I tried paired Oregon with Oregon State.
5. Freshness: if `lastUpdated` is missing or older than 72 hours, do not write FPI for that league. Log `runDateTimeKey`, but do not reject NCAAF because the key is still `20260926040051`.
6. HTML today stores one decimal (`28.2`). `value` is `28.181`. That can move an edge across the 3.0 watch line. Dry-run first and list every game where `abs(value - stored) >= 0.05` or the watch flag would flip. Until that dry run is accepted, write `displayValue` parsed as a float so the series matches `fpi_2026-10-25.csv`.
7. HTML scraper is the fallback only when the JSON request fails or `count` is short. Do not average the two.

## 2. NCAAF availability — official pages only

Blank `Injury Notes` means nobody copied a report. It does not mean healthy.

### SEC

- `https://secsports.com/fbreports` and `https://www.secsports.com/fbreports`
- Both HTTP 200, Date `Mon, 26 Oct 2026 02:46:19 GMT`, 127937 bytes.
- Visible text is the title "SEC Student-Athlete Availability Report: Football" and site chrome. No player table.
- The HTML contains an iframe to `https://app.hdintelligence.com/?source=SEC&sport=Football&conf=SEC&type=report`.
- That URL: HTTP 200, Date `Mon, 26 Oct 2026 02:47:22 GMT`, 7629 bytes, title "HD Intelligence". JavaScript shell. Bundle `https://app.hdintelligence.com/assets/index-CNSNygTD.js` HTTP 200, Date `Mon, 26 Oct 2026 02:48:01 GMT`, 1422580 bytes.
- `POST https://app.hdintelligence.com/api/public-load` with body `{"source":"SEC","sport":"Football","conf":"SEC","type":"report"}` returned HTTP 200, 16 bytes, `{"public": true}`, Date `Mon, 26 Oct 2026 02:48:09 GMT`. GET returned HTTP 405.
- No player rows. I stopped rather than guessing more request bodies.
- The publication clock is not in the HTML I received. I am not treating beat-writer timing as official.

### Big Ten

- Policy URL: `https://bigten.org/news/2026/8/28/big-ten-announces-changes-to-football-availability-reporting-process.aspx`
- I did not re-download that body in the 02:43–02:48 window. A HEAD on the earlier pass was HTTP 200. The cadence below is from that earlier body, not a second fetch tonight.
- Four reports, conference opponents only. Saturday games: submit by 8pm ET / 7pm CT / 5pm PT on each of the three days before kickoff, then a game-day report two hours before kickoff.
- Midweek statuses on that page: Probable, Questionable, Doubtful, Out, Out (1st Half). Game day: Game Time Decision, Out, Out (1st Half). Not listed means Available.
- I did not find a Big Ten URL that serves this week's player report. Trying `app.hdintelligence.com` with `source=B1G` returned the same 7629-byte shell and does not prove the Big Ten uses it.

### Big 12

- Report shell: `https://big12sports.com/sports/2025/8/14/FBreporting.aspx`
- HTTP 200, Date `Mon, 26 Oct 2026 02:47:08 GMT`, 384825 bytes. Title "Big 12 Football Player Availability Reporting". The `2025/8/14` path is the CMS slug.
- Iframe, not a table: `https://app.hdintelligence.com/?source=B12&sport=Football&conf=B12&type=report`
- Policy: `https://big12sports.com/sports/2025/8/21/availability-reporting.aspx` HTTP 200, Date `Mon, 26 Oct 2026 02:46:31 GMT`.
- Text extracted: conference games; daily reports begin three days before the game and are posted at 9 p.m. CT; final report 90 minutes before kickoff. Week statuses on that page: available, probable, questionable, doubtful, out. Game day: available, game time decision, out. The page still says "Beginning with the 2025–26 season."
- PDF linked there: `https://big12sports.com/documents/2026/9/2//Updated_Player_Availability_Policy_9_2_2026.pdf`. I did not open the PDF in this pass.
- Archive shell `https://big12sports.com/sports/2025/8/21/FBReportArchive.aspx` HTTP 200, 02:46:32 GMT. No player table in the HTML.
- Same HD Intelligence limit as the SEC.

### ACC

- Policy: `https://theacc.com/sports/2025/8/28/availability-reporting.aspx`
- HTTP 200, Date `Mon, 26 Oct 2026 02:46:18 GMT`, 353658 bytes.
- Text extracted: conference games. Football reports each day starting three nights before the game, and on game day two hours before kickoff. Before game day: Available, Probable, Questionable, Doubtful, Out. Game day: Available, Game Time Decision, Out. The page defines Probable as 75%, Questionable 50%, Doubtful 25%, Out as will not play.
- PDF link, not opened: `https://theacc.com/documents/2026/8/24//ACC_Availability_Reporting_Policy_2026_27.pdf?id=2940`
- Current report: `https://theacc.com/sports/2025/8/28/availability-reporting-football.aspx` HTTP 200, Date `Mon, 26 Oct 2026 02:46:31 GMT`, 509882 bytes. No table. Iframe `https://app.hdintelligence.com/?source=ACC&sport=Football&conf=ACC&type=report` (HTTP 200, 7629 bytes, 02:47:10 GMT).

### Manual line

One line in `Injury Notes`. Official report only.

```text
[SEC 2026-10-30T01:00Z] HOME: Pos Name Out; Pos Name Questionable | AWAY: none listed
```

- Bracket: conference code and the official report time in UTC.
- Status words from that conference's own list: `Out`, `Doubtful`, `Questionable`, `Probable`, `GTD`, `Out (1st Half)`.
- `none listed` means the report was read and that side had nobody on it.
- Empty field means no report was copied.
- Non-conference games stay empty.
- Do not automate HD Intelligence until a response actually contains players. `public-load` did not.

## 3. Independent points rating

### CFBD SRS

Fits the job: points, not ESPN FPI. I could not read a row.

- `https://api.collegefootballdata.com/srs-ratings.md` HTTP 200, Date `Mon, 26 Oct 2026 02:47:11 GMT`. SRS is schedule-adjusted scoring margin. The page says a rating of 8.0 is roughly eight points better than the average FBS team on a neutral field. Season-to-date. Margin cap and home-field value are not published.
- `GET https://api.collegefootballdata.com/ratings/srs?year=2026` with no key: HTTP 401, Date `Mon, 26 Oct 2026 02:45:47 GMT`. Body says to register a free key at CollegeFootballData.com and send `Authorization: Bearer <key>`.
- Auth doc `https://api.collegefootballdata.com/authentication.md` HTTP 200, 02:45:49 GMT. Same bearer header. Key signup: `https://collegefootballdata.com/key`. Do not commit the key.
- Same 401 that minute for `/ratings/elo?year=2026&week=8` and `/ratings/sp?year=2026`. SP+ is an ESPN model (Connelly) and is not an independence check. I did not re-fetch the Elo methodology page tonight. Elo is not a points margin.

Limits from `https://collegefootballdata.com/api-tiers`, HTTP 200, Date `Mon, 26 Oct 2026 02:45:48 GMT`. The page does not say SRS is excluded. I did not confirm with a key.

- Free: 1,000 calls/month, key required
- Academic (.edu): 3,000, free
- Tier 1: 5,000, $1/month
- Tier 2: 30,000, $5/month
- Tier 3: 75,000, $10/month
- Tier 4: 125,000, $15/month
- Tier 5: 200,000, $20/month
- Tier 6: 500,000, $30/month

`https://api.collegefootballdata.com/usage-and-access` points at that tiers page and says the numbers can change. Last modified shown there: October 25, 2026. No commercial-use sentence on the tiers page that I was given.

I have not seen a 200 SRS body, so I do not know the team-name field. One call may be the whole season if the API returns every team at once. That is a guess about paging. Do not wire it until a dry run with `CFBD_API_KEY` prints one row.

Later log-only fields: `Home SRS`, `Away SRS`, `SRS Pulled At`. Compare `home_srs - away_srs` to `home_fpi - away_fpi`. Do not replace FPI. Do not add the model's HFA on top of SRS without a written reason: the SRS doc says home field is already inside the rating.

### Not usable this pass

- Massey `https://masseyratings.com/ranks?s=cf&sym=cmp`: HTTP 200, Date `Mon, 26 Oct 2026 02:46:20 GMT`, 6896 bytes, title "Massey Ratings - College Football Rankings". Text says "Please wait while the data loads." No teams. Loader `https://masseyratings.com/inc/stamp-getjson.js?v=20260911` is obfuscated. I did not decode it. The page links `https://www.kaggle.com/masseyratings/rankings/data`. I did not open Kaggle and I did not confirm a points scale.
- Sagarin `https://sagarin.com/sports/cfsend.htm`: TLS verification failed (self-signed certificate). I did not read the page.
- No other free points-scale feed returned a team rating I could quote.

## 4. Weather — log only

Do not add weather to `model_home_margin`. There is no graded CLV test.

### ESPN venues have no coordinates

`GET https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/venues/3673` HTTP 200, Date `Mon, 26 Oct 2026 02:44:51 GMT`, 554 bytes. Keys: `$ref`, `id`, `guid`, `fullName`, `address`, `grass`, `indoor`, `images`. No latitude or longitude.

Lumen Field id `3673`: Seattle, WA, zip `98134`, `grass` false, `indoor` false.

`https://site.api.espn.com/apis/site/v2/sports/football/nfl/venues/3673` was HTTP 404.

NFL scoreboard at Date `Mon, 26 Oct 2026 02:45:19 GMT`, 14 events. `indoor` is ESPN's flag. I am not calling any of these retractable. ESPN does not send a roof type.

- 3673 Lumen Field, indoor false, KC at SEA, kickoff `2026-10-26T00:20Z`
- 1781 Stade de France, indoor false, PIT vs NO, `2026-10-25T13:30Z`, city Saint-Denis, France
- 5348 Mercedes-Benz Stadium, indoor true
- 3810 Nissan Stadium, indoor false
- 5239 U.S. Bank Stadium, indoor true
- 3839 MetLife Stadium, indoor false
- 3628 Bank of America Stadium, indoor false
- 3814 M&T Bank Stadium, indoor false
- 3891 Reliant Stadium, indoor true
- 3970 State Farm Stadium, indoor true
- 3727 Ford Field, indoor true
- 6501 Allegiant Stadium, indoor true
- 3933 Soldier Field, indoor false
- 3806 Lincoln Financial Field, indoor false

NCAAF the same hour: event `401859185`, venue id `3738` Gillette Stadium, Foxborough, MA, indoor false. No coordinates.

### The one coordinate I fetched

`GET https://nominatim.openstreetmap.org/search?q=Lumen+Field%2C+Seattle&format=jsonv2&limit=3`

HTTP 200, Date `Mon, 26 Oct 2026 02:45:50 GMT`.

- lat `47.5953459`
- lon `-122.3316443`
- display name: Lumen Field, 800, Occidental Avenue South, Yesler Terrace, Seattle, King County, Washington, 98134, United States
- type `stadium`
- osm relation `5838734`, place_id `324460981`
- licence returned: `Data © OpenStreetMap contributors, ODbL 1.0. http://osm.org/copyright`

That is the only coordinate pair in this note. I did not geocode Stade de France or Gillette. Do not use `47.5952, -122.3316`. That pair was not fetched.

### Forecasts at that pair

Open-Meteo, no key. HTTP 200, Date `Mon, 26 Oct 2026 02:47:10 GMT`.

`https://api.open-meteo.com/v1/forecast?latitude=47.5953459&longitude=-122.3316443&hourly=temperature_2m,precipitation_probability,wind_speed_10m,wind_gusts_10m&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=UTC`

Hour `2026-10-26T00:00` (20 minutes before kickoff `2026-10-26T00:20Z`): 56.5 F, precipitation probability 8, wind 3.7 mph, gust 11.6 mph.

Terms `https://open-meteo.com/en/terms`, HTTP 200, same minute. Free non-commercial use: under 10,000 calls/day, 5,000 per hour, 600 per minute. CC-BY 4.0. They may block an IP without notice. Attribute Open-Meteo. I did not find an SLA. Confirm before any public or commercial use.

NWS:

- `GET https://api.weather.gov/points/47.5953459,-122.3316443` HTTP 200, Date `Mon, 26 Oct 2026 02:47:11 GMT`. Grid SEW 125, 67. City Seattle, WA. A User-Agent was sent.
- Hourly `https://api.weather.gov/gridpoints/SEW/125,67/forecast/hourly` HTTP 200, Date `Mon, 26 Oct 2026 02:47:53 GMT`. `updateTime` `2026-10-25T22:06:01+00:00`. First period starts `2026-10-25T18:00:00-07:00`. The 17:00 local kickoff hour was already gone. I am not quoting an NWS temperature at kickoff.
- NWS will not cover Saint-Denis. Venue `1781` stays blank until it is geocoded.

### How to log it

Cache venues. Do not geocode every run. Store ESPN venue id, name, city, region, lat, lon, source URL, fetch time, and OSM id when Nominatim was the source. Refresh only when the id is new or ESPN's name or city changes.

Fields, not Splash, not the margin:

- `Weather Temp F`, `Weather Wind Mph`, `Weather Gust Mph`, `Weather Precip Pct`
- `Weather Valid Hour` in UTC
- `Weather Source`, for example `Open-Meteo CC-BY lat=47.5953459 lon=-122.3316443 hour=2026-10-26T00:00Z`
- `Weather Pulled At`
- `ESPN Indoor` copied as sent
- `Roof Class`: `unknown`, `fixed_dome`, `retractable`, or `open`. Default `unknown`. Do not set this from `indoor`.

One Open-Meteo call per venue per pull. I did not test a multi-location request. An every-three-hours sync of the slate is under 10,000 a day. Use the hour that contains kickoff. If that hour is missing, leave weather blank. Do not substitute a later hour without saying so.

Put a weather number into the margin only after graded CLV moves, in its own PR.
