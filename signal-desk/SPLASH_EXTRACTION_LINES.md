# File 1: Splash Sports line extraction

Use the owner-run browser extraction while the actual contest board is open. This prompt does not authorize betting or publication. The full [import contract](SPLASH_IMPORT.md) defines validation and the [chat prompts](CHAT_PROMPTS.md) handle approved submission.

## Owner steps

Open the intended NFL/NCAAF slate, load all applicable dates/tabs/pages, and paste the complete prompt below. Save only the returned JSON with its actual date_code as the filename. Submit soon after observation, preferably within four hours; the import hard limit is 24 hours.

```text
Extract the complete intended NFL/NCAAF slate from the actual Splash
Sports contest board open in my browser. Read only that owner's source,
including its accessible game details, league tabs, pagination and
show-more/lazy-loaded entries. Do not submit or change picks or accounts.
Use no memory, outside schedule or invented team-name expansion.

Build the games array FIRST from actually observed games. Deduplicate
repeat displays. Establish each league from its actual section/details.
Compute game_count by counting the finished array's NFL and NCAAF tags.
Independently recount and require their sum to equal games.length.
Do not copy a page-wide widget into game_count. Preserve widget values
and their source scope separately in notes. Do not reclassify, invent
or omit games to make a counter agree. Describe inaccessible coverage
or uncertain classification in warnings and retain all observed rows.

Copy team labels as shown; use a full name only if source details provide
it. Explicit A at B or A @ B establishes away=A, home=B; missing separate
home/away badges alone does not make that explicit notation uncertain.
Visual order alone does not establish orientation. Record actual
orientation evidence in notes. Set home_away_certain false if unresolved.
Keep unavailable venue and game_status null; absent optional status is
an informational note, not invented live/final status.

Use the actual current observation clock. If unavailable, ask me.
Record equivalent extracted_at_utc and extracted_at_central instants,
using America/Chicago with the game's correct CST/CDT rules.
For every game preserve kickoff_as_shown, its source timezone, actual
game date and converted Central kickoff, including date rollover.
If date/time/year/zone is unknown, use null and a specific warning.
Never manufacture midnight, copy extraction time as kickoff, or infer
a game year merely from today's year or a contest title.

Copy each team's OWN signed spread, actual total and displayed American
prices. Use number 0 for PK. Away/home spreads must be opposites; preserve
and flag discrepancies rather than fixing signs. Preserve displayed
+100 exactly, including when the board consistently uses even money.
Use null for unavailable prices. Do not insert -110 or estimate a
moneyline from a spread. Preserve unsupported extra markets separately.

Return one original JSON object, without a Markdown fence or commentary:
schema: "signal-desk.splash-lines.v1"
source: "Splash Sports Lines"
date_code: SPL-L-YYYYMMDD-HHMM from actual Central observation time
extracted_at_central: YYYY-MM-DD HH:MM:SS CST or CDT
extracted_at_utc: ISO 8601 UTC with Z, same observed instant
page_url, page_title, contest_name, page_timezone: actual source or null
game_count: NFL and NCAAF integer counts computed from games
notes: informational source limitations and preserved page-widget scope
warnings: unresolved required observations or coverage concerns only
games: complete observed array, each object containing:
  source: "Splash Sports Lines"
  date_code: the same actual parent code
  league: NFL or NCAAF from source classification
  away_team, home_team: observed source names
  home_away_certain: boolean with source evidence in notes if helpful
  venue: actual observed value or null
  kickoff_as_shown: original displayed date/time text
  kickoff_central: actual YYYY-MM-DD HH:MM or null
  kickoff_tz: CST or CDT or null
  game_status: actual observed status or null
  away_spread, home_spread, total: numeric observed values or null
  away_spread_price, home_spread_price, over_price, under_price:
    actual American numeric prices or null
  away_ml, home_ml: actual American numeric prices or null
  other_markets: array of actual market/selection/line/price/source text

Before output, check the array-derived counts again. Preserve truthful
warnings rather than declaring an unresolved source import-ready.
The JSON may contain private contest/account details; saving or extracting
does not authorize publishing those details to a public repository.
```
