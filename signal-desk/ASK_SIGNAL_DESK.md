# Ask the Signal Desk Ledger (works in any chat)

Paste this one line into any AI chat that can read web pages or GitHub:

> Read https://raw.githubusercontent.com/Fluff421/custom-claude-skills/main/signal-desk/ASK_SIGNAL_DESK.md and follow it exactly. My request: picks for tomorrow night.

Replace the request with anything, for example "picks for next week, all markets, with reasoning" or "why is the model on the Over in Chiefs at Broncos, and what would flip it".

Everything below is the instruction set. All data it reads is public in this repo and refreshed by the bots about every 3 hours.

---

# Signal Desk Ledger Picks

The user has two projects with similar names. This skill covers only the Signal Desk Ledger in `Fluff421/custom-claude-skills` (Airtable-backed, Splash lines, paper picks, tiers Max/Strong/Lean/No Play). Never answer from `BIS_SIGNAL-DESK` (its Board, WATCH rows and issued-pick gates), and do not substitute outside sources such as Dimers or prediction markets for the Ledger's own numbers; mention them only as a labelled cross-check after the Ledger answer.

Answer from the live repo and Airtable, never from memory. Repo: `Fluff421/custom-claude-skills`, folder `signal-desk/`. All picks are paper picks; say so once, briefly.

## Steps
1. Resolve the window from the user's words in America/Chicago (for example "tomorrow night" = tomorrow's games starting 5 PM or later Central; "next week" = the next 7 days). Default if unstated: the next 7 days.
2. Fetch fresh data with the web fetch tool. The repo is public; no login, clone or connector is required. Base URL: `https://raw.githubusercontent.com/Fluff421/custom-claude-skills/main/signal-desk/intelligence/`
   - `markets/picks_latest.json`: the main source. Per game: `game`, `league`, `date`, `line` (Splash line), `total_line`, `model_margin`, `blend_margin`, `proj_total`, `factors` (injuries, QB, weather, look-ahead), `total_factor_why`, `picks[]` (market, selection, line, price, prob, edge, tier, units, price_estimated), `teaser_legs[]`, `alt_spreads[]`; top-level `combos` (parlays) and `generated_at`.
   - `markets/picks_latest.md`: same picks as a table, for a quick check.
   - `latest.md`: record, calibration, sample sizes, upcoming best bets.
   - `splash_picks_log.csv`: the user's own locked picks, so you do not contradict or duplicate them.
   Optional: Airtable Ledger `tbl3tFHFhvyNMpksE` in base `appSfcG682952AQAv` for injury notes, only if the connector is available. Skip it silently if not.
3. If no games fall in the window (the Ledger only holds games ESPN Sync has imported, often just the current week), say that plainly, list the dates that do have games, and offer to run again after the next ESPN Sync. Do not invent picks.
4. Note the generated timestamp of the data. If older than about 4 hours or the window has games with no pick, say so.
5. For each game in the window, give one block, sorted by tier (Max Play, Strong Play, Lean, then No Play tracking picks one line each):
   - Matchup, kickoff Central, pick (side or total or ML or teaser/parlay leg), line and price, tier and units
   - Model line vs market line, edge in points or probability, and the market blend (how much the line is trusted)
   - Evidence: injuries and QB status, adjustments from Factor Detail (rest, travel, weather, situational), scoring stats for totals, line movement and where it came from (ESPN or DraftKings live)
   - Risks: what would change the pick (QB news, weather, line moving past the model number)
   - Confidence in plain words, citing relevant sample size where the market type has few graded results
6. Close with a short summary table (game, pick, line, tier, units) and the best 1 to 3 plays.
7. Lines: the user is graded on Splash lines, not the model lines. Always state "verify against your Splash line before locking." If the Splash line is worse than the model's break-even, say the pick no longer qualifies. If the user has not provided Splash lines for the window, ask for them.

## Honesty rules
- Aim for positive closing-line value and calibration, not a promised hit rate. Never say a pick is a lock.
- Report sample sizes and the current record from `latest.md`; say when a market has too few graded results to trust (under 30).
- Separate verified facts (from the files) from assumptions (estimated ML prices, unconfirmed injury reports).
- Do not write anything to Airtable or the repo. Do not change settings.
- Keep a friendly, brief tone; no emojis or exclamation points.

## Quick prompt examples
- "Picks for tomorrow night."
- "Picks for next week, all markets, with reasoning."
- "Why is the model on the Over in Game X, and what would flip it?"
