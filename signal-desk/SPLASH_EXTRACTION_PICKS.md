# File 2: Splash Sports pick extraction

Run this owner-only extraction separately for Pending/Open and Completed/Settled pages. Save the actual JSON, not these instructions. It preserves source observations without authorizing betting, publication, result correction or Airtable writes.

## Owner steps

Expand every ticket and leg and inspect accessible matchup details before running the prompt. Submit pending observations within 12 hours and completed observations within 24 hours, preferably within four hours. A completed ticket may use an actual observed game date when the source does not expose kickoff; matching dates are not placement or settlement dates.

```text
Extract the actual Splash Sports ticket page open in my browser,
including accessible ticket/matchup details. Use only this owner's
source. Do not place/change picks or accounts, publish, or use memory.
Detect page_type pending or completed; ask if unclear. Extract separately,
never mix page types. Load all intended pages and expand every ticket.
For completed history include the last seven days and older unresolved
items when accessible; describe actual visible coverage.

Preserve each single/parlay/teaser as one ticket with every observed leg.
Unsupported structures stay represented with an explicit warning,
not silently removed. Use a real ticket ID when shown. Otherwise label
a stable source-derived identity built from actual observed ticket
metadata and the complete ordered selections. Do not use the current
clock as a pretend placement ID or silently correct a known ID.

Copy the official recorded ticket line, not the current game-board
number. Preserve numeric signed lines, PK=0, and actual American price.
Null spread/total prices are permitted when not displayed. Moneylines
need their actual quoted price. Do not default to -110 or +100.

For teasers, teased_line is the explicitly displayed final adjusted
number. If the ticket explicitly labels its only number as final,
copy that number to teased_line and line. Keep base_line null unless
it is actually shown. Never add/subtract six to invent a missing
base or final number. If the printed number's meaning is unclear,
leave teased_line null, preserve source text and record a warning.

Copy both teams, league and source evidence of orientation.
Explicit A at B or A @ B establishes away=A and home=B.
Use full team names only if the source provides them; observed nicknames
are acceptable labels. The importer may expand a selection only after
uniquely matching an existing dated game and its two teams.
Do not invent a team dictionary or infer an uncertain league.
Use selection Over or Under for totals, with the number in line.
For a spread or moneyline, selection is the observed team label.

Stamp the actual current observation instant in UTC and America/Chicago.
If the clock is unavailable, ask me. Never copy an old extraction stamp.
Preserve displayed ticket dates/times separately and exactly.
For each leg capture actual kickoff date/time and source timezone if
shown, converting with the correct CST/CDT offset and date rollover.
If completed history shows the actual game date but no kickoff time,
set game_date_central to that observed YYYY-MM-DD and kickoff_central
and kickoff_tz null. Describe the missing time in notes; do not invent it.
For pending tickets, missing actual kickoff remains a warning.
If no actual GAME date is available, game_date_central stays null with a
warning. Never substitute placement/settlement/extraction time, a ticket
ID date, a final-whistle timestamp, today's year or contest title.
If the displayed year conflicts with other source evidence, retain it
and flag the conflict. Ask me before changing any year.

Preserve actual stake, payout, potential_payout, quoted payout_multiplier,
contest and entry names if displayed; otherwise null. Preserve actual
reported ticket/leg outcomes and scores as source metadata, not as
independently verified results or hypothetical calculated winnings.
For pending tickets do not manufacture a final result.

For this NEW capture, return one original UTF-8 JSON object on a single
line, without indentation, a Markdown fence, commentary, BOM or terminal
newline. Keep every whole ticket, leg and observed field; never drop
observations to make the file smaller. This compact output rule does NOT
authorize minifying, reserializing or changing an existing original.
Use this structure:
schema: "signal-desk.splash-picks.v1"
source: "Splash Sports Picks"
date_code: SPL-P-YYYYMMDD-HHMM for pending, SPL-C-YYYYMMDD-HHMM for completed
extracted_at_central: actual YYYY-MM-DD HH:MM:SS CST or CDT
extracted_at_utc: actual ISO UTC instant with Z
page_type: pending or completed
page_url, page_title, contest_name, entry_name: actual value or null
coverage: actual visible source coverage with no inferred year changes
ticket_count: integer counted from the complete tickets array
notes: informational limitations that do not hide required uncertainty
warnings: unresolved required observations, coverage or date conflicts
tickets: array, each object containing:
  ticket_id: stable actual/source-derived identity
  ticket_id_basis: source evidence if useful
  ticket_type: single, parlay, teaser, or unsupported other with warning
  source, date_code: exact parent source and code
  placed_at_central, locked_at_central: observed times or null
  stake, potential_payout, payout, payout_multiplier: actual values or null
  reported_result: actual source result or null
  legs: full ordered array, each object containing:
    league: NFL or NCAAF, or null with warning if unresolved
    away_team, home_team: source labels or null
    home_away_certain: boolean based on explicit source evidence
    game_date_central: actual GAME date YYYY-MM-DD or null
    kickoff_central: actual GAME kickoff YYYY-MM-DD HH:MM or null
    kickoff_tz: actual CST/CDT label or null
    kickoff_as_shown: actual source text or null
    market: spread, total, moneyline, or unsupported other with warning
    selection: observed team label or Over/Under
    line: actual recorded number, not current board line
    price: actual American numeric odds or null
    base_line: observed teaser base or null
    teased_line: explicitly observed final teaser number or null
    reported_result, final_score: actual displayed values or null
    selection_as_shown: original text if needed

Recount tickets and legs before output. Keep all source IDs and official
numbers unchanged; existing-ticket deduplication happens in the importer.
Do not clear real warnings merely to claim readiness. These files may
contain private contest/account details; extraction is not permission
to publish them in a public repository.
```
