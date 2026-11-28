# Signal Desk Research Feed (Grok pilot)

**Branch:** `research/grok-feed`  
**Purpose:** Attributable observations (injuries, weather, ops health) for later ingestion. Research only. Never writes to main production paths.

## Directory contract
- `injuries_ncaaf/YYYY-MM-DD.csv` — conference availability (SEC/ACC/Big 12/Big Ten + independent notes)
- `weather/YYYY-MM-DD.csv` — pregame forecasts for outdoor/unknown-roof games
- `ops/YYYY-MM-DD.md` — daily Actions + LEDGER surface health
- `reference/` — historical research notes (copies; originals remain on their branches)
- `venues.csv` — (future) cached verified coordinates with attribution
- `manifest-YYYY-MM-DD.json` — schema version, row counts, real vs schema-only labels

## Rules observed in this pilot
- Official sources only; every observation has `source_url` + `checked_at_utc`.
- Report publication time ≠ retrieval time.
- Blank / not_published ≠ healthy.
- Roof class ≠ game-day open/closed status.
- Weather and injuries remain log-only until a separate reviewed integration exists.
- No credentials, no main edits, no schedule activation from this branch.

See the review instructions message for full authority and validation requirements.
