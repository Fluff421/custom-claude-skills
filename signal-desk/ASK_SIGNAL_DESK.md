# Ask the Signal Desk Ledger (works in any chat)

Paste this one line into any AI chat that can read web pages or GitHub:

> Read https://raw.githubusercontent.com/Fluff421/custom-claude-skills/main/signal-desk/ASK_SIGNAL_DESK.md and follow it exactly. My request: picks for tomorrow night.

This file is the portable copy of the Perplexity skill `signal-desk-ledger-intelligence`. Keep it in sync with the skill when either changes.

---

# Signal Desk Ledger Intelligence

The user's continuously learning NFL and NCAAF paper-betting system. Always answer from live data, never from memory or outside sources.

## Which project
- This skill = Signal Desk Ledger: GitHub `Fluff421/custom-claude-skills`, folder `signal-desk/`, Airtable base `appSfcG682952AQAv` (Ledger table `tbl3tFHFhvyNMpksE`).
- Different project: `Fluff421/BIS_SIGNAL-DESK` (separate NFL board with WATCH rows and issued-pick gates). Never use it for this skill unless the user names it.
- Do not substitute Dimers, prediction markets or other public picks for the Ledger's numbers. Mention them only as a labelled cross-check after the Ledger answer.

## Access order
1. Public files (works in any chat, no login): `https://raw.githubusercontent.com/Fluff421/custom-claude-skills/main/signal-desk/<path>`. Start with `intelligence/markets/picks_latest.json`, `intelligence/latest.md`, `MODEL.md`.
2. If a GitHub connector or `gh` exists, use it for any repo or branch the user names, including PRs, workflow runs and the `research/grok-feed` branch.
3. If an Airtable connector exists, read the Ledger, Model Parameters `tblTqY4CnU08ce1s9`, Calibration Log `tblN7NyoPdOve792d`. Read-only.
4. If Perplexity memory exists, read `memory/knowledge/projects/signal-desk-ledger.md` for decisions and history.
5. If none of these can be read, say exactly which could not be read and stop. Never invent picks or data.

The data map and answer playbooks follow below in this file.

## Core rules
- All picks are paper picks. Every game gets a pick; tier No Play with 0 units is a tracking pick, not a recommendation. Max and Strong stay paper with the unit cap.
- The user is graded on the Splash line locked at pick time. Imported line = early-week line; the gap is line movement, never bad data. State "verify against your Splash line before locking."
- Goal is positive closing-line value and calibration, not a promised hit rate. Never say lock or guarantee.
- Respect sample minimums: 20 per tier, 30 per league and market, 30 games with factor records and 10 non-zero per factor. Say when evidence is below them.
- Separate verified facts (from files) from assumptions (estimated ML prices, unconfirmed injuries).
- Check `generated_at`; flag data older than 4 hours. If the window has no games, list the dates that do.
- Read-only. Never write to Airtable or the repo, never write Splash fields, never change variables, merge or push. Propose changes as a short list for the user to approve.
- Missing Splash lines or manual data: ask the user to provide them.
- Friendly, brief, no emojis, no exclamation points.

## Continuous learning
Each answer should also report what the system learned: read `intelligence/learning_log.csv` (tuning change events), `learning_state.csv` (daily state), `markets/scorecards.json` and `market_params.json`. If they are empty, say learning has not triggered yet and why (sample minimums). Newest automation findings live in `intelligence/splash_picks/`, `intelligence/grok_notes/`, `data/ops_status.json`.

---

# Data map (paths relative to `signal-desk/` in Fluff421/custom-claude-skills, main branch)

## Picks and markets
- `intelligence/markets/picks_latest.json`: per game `game, league, date, frozen, line (Splash), total_line, model_margin, blend_margin, proj_total, factors[], total_factor_why[], picks[] (market, side, selection, line, price, price_estimated, prob, edge, edge_unit, tier, units), teaser_legs[], alt_spreads[]`; top-level `combos` (parlays by league), `generated_at`, `date`. Window is today through 7 days.
- `intelligence/markets/picks_latest.md`: table form. `picks_log.csv`: every priced pick with results once graded. `lines_log.csv`: ESPN/DraftKings line history (movement and CLV). `scorecards.json`: per league and market record and Brier. `market_params.json`: learned per-market settings.
- `intelligence/latest.md` and `intelligence/data/YYYY-MM-DD.json`: daily intelligence report (record, calibration, best bets, by-market sections, factor evidence).

## Learning
- `intelligence/learning_log.csv`: change events (date, league, market, setting, old, new, evidence, sample_size, source). `learning_state.csv`: daily state (graded, graded_with_factor_record, brier, sigma, market_k, scale_* per factor).
- Model Parameters (Airtable): per league Sigma, Market Blend K, thresholds, tier multipliers. Calibration Log (Airtable): calibration history.

## Your own picks
- `intelligence/splash_picks_log.csv`: locked-line picks compared with the model (imported_line, locked_line, movement_for_you, model side and tier at import and lock, side_changed, ticket_prob, ticket_break_even). `intelligence/splash_picks/*.md`: each comparison run, readable.
- Splash lines inside the Ledger are the hand-entered `Vegas Implied Home Margin` and `Over/Under Line`.

## Ledger (Airtable base appSfcG682952AQAv, table tbl3tFHFhvyNMpksE, Record Type = Game)
Fields include Game, League, Date, Home/Away Team, FPI values, Model Home Margin, Vegas Implied Home Margin, Edge, Confidence Tier, Recommended Side, Suggested Units, Closing Spread (Home), scores, Spread Result, O/U Result, Injury Notes, Weather Note, Factor Detail, Scoring Detail.

## Operations
- `data/ops_status.json`: ledger health and per-workflow health and `schedule_health`. `data/graded_picks.csv`, `data/snapshot.json`: snapshot exports.
- `intelligence/grok_notes/*.md` and `intelligence/grok_notes/availability_{nfl|ncaaf}/YYYY-MM-DD/qb_starters.csv`: Grok's injury and QB notes (read by the model once merged to main). Branch `research/grok-feed` is the older feed.
- Docs: `MODEL.md` (model spec, current rules), `LEDGER.md`, `intelligence/README.md`, `intelligence/ROADMAP.md`, `research/SOURCES.md`.

## Workflows (GitHub Actions, UTC)
ESPN Sync :27 every 3h; Pick Engine :47 every 3h and right after each successful Context & Calibrate run (also markets); Close & Grade :37 hourly; NCAAF Injury Pull :33 every 3h Wed-Sat, 14:33 Sun-Tue; Context & Calibrate 13:43 daily (market learning, learning_log); Snapshot 13:17/14:17 gated to 8:17 AM Central; BIM grader :27 every 2h Sun, Mon, Thu, Fri, Sat; Splash compare manual dispatch.
Repo variables control live writes (for example FACTOR_MODE=live, MARKETS_LIVE, MARKET_LEARN_LIVE, REPRICE_LIVE). Do not change them; ask the user.

## Perplexity automations (user account)
Daily briefing `7d7639b8-db78-4f6c-941f-581bf17d0721` (8:30 AM Central); Splash picks vs model on demand `aea703e2-c24b-4251-9ef1-a6956f28c596`; weekly Splash spreads request `0beca3da-f5fa-4b5a-986d-f5bf7698c425` (Mondays 9 AM Central); weekly picks briefing `9571d4dc-d864-4276-982e-0a4e1ac5fb1a` (Sundays 6 PM Central); on-demand picks `5e099cdd-3ee0-426f-bf79-bcda576019a4` (Run now). In Perplexity, read their run history for the latest outputs. Grok runs separate automations (ops check 9 AM, injuries 9:30 PM, learning note Monday 10 AM Central); their results arrive as PRs into `intelligence/grok_notes/`.


---

# Answer playbooks

## Picks for a window
Window in America/Chicago. Per game in tier order (Max, Strong, Lean, then No Play one line each): matchup and kickoff, pick, line, price, tier, units; model vs market line, edge, blend (`blend_margin` vs `model_margin`); evidence from `factors` and `total_factor_why`; risks (QB news, weather, movement past the model number); confidence with sample sizes. End with a summary table and the best 1 to 3 plays. When every pick for a game is No Play, say pass and name the closest watch item.

## Why this pick / what would flip it
Show the numbers: line, model margin or projected total, edge needed for each tier (`MODEL.md`), factor contributions. State the line or news change that flips the side.

## Performance and calibration
From `latest.md`, `scorecards.json`, `learning_state.csv`: record, Brier, per-market results, CLV if present, tier results. Always give n. Under the sample minimums, call it noise.

## What has the system learned
From `learning_log.csv` and `learning_state.csv`: each change event with old, new, evidence, n. If none: say gates not met and how many more graded games are needed.

## Splash comparison
From `splash_picks_log.csv` and latest `splash_picks/*.md`: your locked line vs imported vs model at lock, movement, side_changed, ticket probability vs break-even. Grade only at the locked line.

## Ops health
From `data/ops_status.json` (workflow health, schedule_health, ledger counts, Splash vs ESPN gaps of 3+ points). Distinguish real failures from expected empties (no factor records until games finish, empty learning log, estimated ML prices). For deeper checks use GitHub run history if available.

## Improvement suggestions
Offer concrete next steps (data to supply, thresholds near their gates, a variable to flip) as a list for approval. Never act on them.
