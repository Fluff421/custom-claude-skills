# File 1: Splash Sports line extraction

Version 2026-11-16. Owner-run extraction while the actual contest board is open. It works in Gemini in Chrome (side panel) or in Perplexity Computer's browser. This prompt does not authorize betting or publication. The [import contract](SPLASH_IMPORT.md) defines validation, [`splash_preflight.py`](splash_preflight.py) checks the result before submission, and [CHAT_PROMPTS.md](CHAT_PROMPTS.md) handles the approved submission.

## Why this version exists

The 2026-11-16 capture `SPL-L-20261116-1356` was rejected with `game_count must contain nonnegative integer counts`. The extractor wrote the page widget number `64` as a bare integer, while the games array held 79 games (13 NFL, 66 NCAAF), and it still reported no warnings. Root causes in the old prompt: `game_count` had no literal shape, there was no separate place for page widgets, there was no mandatory self-check that turns a mismatch into a warning, and `notes` had no defined type. This version fixes each one with an exact skeleton, enums and a final checklist.

## Owner steps

1. Open the intended NFL/NCAAF slate. Load every league tab, date and page, and press every show-more button.
2. Paste the complete prompt below. If the reply starts with `STOP:`, fix what it names and run it again.
3. Save only the returned JSON, named exactly `<date_code>.json`.
4. Run the preflight (CHAT_PROMPTS.md, "Perplexity Computer route") and fix every ERROR by re-extracting, never by hand-editing.
5. Submit within 4 hours if you can. The importer's hard limit is 24 hours from capture to processing, including any owner review.

```text
TASK: Extract Splash Sports lines into ONE JSON object for Signal Desk.

SOURCE RULES
- Read only the Splash Sports contest board open in my browser, including
  its league tabs, dates, pagination, show-more and game detail panels.
- Do not place, change or submit picks. Do not change any account setting.
- Use no memory, no outside schedule, no other website and no guessed data.

HARD STOPS. Reply with one line starting "STOP:" and no JSON when:
- the page is not a Splash Sports contest board with NFL or NCAAF games;
- you cannot read the current date and time (ask me for it);
- a league tab, page or show-more list could not be loaded.

STEP 1. Build the games array first.
- One object per real game actually shown. Remove repeat displays of the
  same game. Never invent, merge or drop a game to make a count agree.
- league: exactly "NFL" or "NCAAF", from the board's own section or detail.
- away_team, home_team: copy the labels exactly as shown. Use a longer
  name only if the board itself shows it.
- Orientation: "A at B" or "A @ B" means away_team = A, home_team = B.
  Set home_away_certain to true only with that explicit notation or an
  explicit home/away badge. Screen order alone is NOT evidence; then set
  false and add a warning naming the game.

STEP 2. Times. All Central times use America/Chicago.
- kickoff_as_shown: the game's kickoff text exactly as displayed,
  including its zone, e.g. "Tue, Nov 17, 6:00 PM EST".
- kickoff_central: that kickoff converted to Central, "YYYY-MM-DD HH:MM",
  24-hour clock, with the correct date if the conversion crosses midnight.
- kickoff_tz: ONLY "CST" or "CDT" (CST from early November to mid March,
  otherwise CDT), or null. Never write EST, ET, PST, UTC or any other
  zone here. The source zone stays inside kickoff_as_shown.
- If a kickoff date, time or year is not shown, set kickoff_central and
  kickoff_tz to null and add a warning naming the game. Never use the
  extraction time, midnight, today's year or the contest title instead.
- Use the real current clock for extraction. extracted_at_central is
  "YYYY-MM-DD HH:MM:SS CST" (or CDT). extracted_at_utc is the SAME
  instant as "YYYY-MM-DDTHH:MM:SSZ". date_code is
  "SPL-L-YYYYMMDD-HHMM" from the Central date and minute.

STEP 3. Numbers.
- away_spread, home_spread: each team's own signed spread as a number.
  PK = 0. They must be exact opposites. If the board shows otherwise,
  copy what is shown and add a warning; never fix a sign.
- total: the game total as a number.
- away_spread_price, home_spread_price, over_price, under_price,
  away_ml, home_ml: American odds as numbers, e.g. 100, -110, 500, -690.
  This contest uses Even line odds, so +100 shown on spreads and totals
  is correct; write 100. Use null when a price is not shown. Never
  insert -110 and never estimate a moneyline from a spread.
- Numbers are JSON numbers, not strings. No "+" sign, no quotes.
- Markets other than spread, total and moneyline go in other_markets as
  objects {"market","selection","line","price","as_shown"}; else [].

STEP 4. Counts and page widgets.
- game_count is an OBJECT with exactly two integer keys counted from the
  finished games array: {"NFL": <count of NFL games>, "NCAAF": <count of
  NCAAF games>}. NFL + NCAAF must equal the number of games in the array.
- NEVER copy a page header, banner, badge or widget number into
  game_count. Record those in page_widgets as
  {"label": "...", "value": "...", "scope": "..."} instead.

STEP 5. notes and warnings. Both are JSON arrays of strings.
- notes: informational facts only (for example "Board uses Even odds").
- warnings: ONLY problems that are still unresolved: a missing kickoff,
  uncertain orientation, a spread sign mismatch, a tab that would not
  load, a count that does not reconcile. Any warning blocks import until
  I resolve it, so never hide a real problem in notes, and never invent a
  warning. Use [] when there is none.

OUTPUT FORMAT. Exactly this key order and these keys. Do not repeat
source or date_code inside each game; the parent values apply.
{"schema":"signal-desk.splash-lines.v1","source":"Splash Sports Lines","date_code":"SPL-L-YYYYMMDD-HHMM","extracted_at_central":"YYYY-MM-DD HH:MM:SS CST","extracted_at_utc":"YYYY-MM-DDTHH:MM:SSZ","page_url":"... or null","page_title":"... or null","contest_name":"... or null","page_timezone":"... or null","game_count":{"NFL":0,"NCAAF":0},"page_widgets":[],"notes":[],"warnings":[],"games":[{"league":"NCAAF","away_team":"...","home_team":"...","home_away_certain":true,"venue":null,"kickoff_as_shown":"...","kickoff_central":"YYYY-MM-DD HH:MM","kickoff_tz":"CST","game_status":null,"away_spread":0,"home_spread":0,"total":0,"away_spread_price":100,"home_spread_price":100,"over_price":100,"under_price":100,"away_ml":null,"home_ml":null,"other_markets":[]}]}
- venue and game_status: the shown value or null. Do not invent status.
- Return the JSON object only, on ONE line: no Markdown fence, no
  commentary before or after, no indentation, no trailing newline.
- Keep every observed game and field. Never shorten the file by dropping
  observations.

FINAL SELF-CHECK. Do every item silently, then output.
1. Count NFL and NCAAF objects in games one more time; game_count must
   equal those counts and their sum must equal the array length. If you
   cannot make them agree truthfully, keep the true array counts and add a
   warning that explains the difference.
2. Every kickoff_tz is "CST", "CDT" or null. None is EST or ET.
3. Every away_spread equals minus home_spread, or a warning names it.
4. Every price is a number or null, never a string, never invented.
5. extracted_at_central and extracted_at_utc are the same instant and the
   date_code matches the Central date and minute.
6. No game appears twice, in either orientation.
7. The output parses as one JSON object.

PRIVACY: the JSON contains contest and account details. Producing it does
not authorize publishing it.
```
