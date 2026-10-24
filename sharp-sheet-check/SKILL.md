---
name: sharp-sheet-check
description: Lightweight, chat-only sports-betting analytics skill for NFL and NCAAF spread, total, moneyline, and parlay picks — a fast manual companion to the Betting Intelligence Machine (BIM) v2.0, not a replacement for it. Runs entirely through web search in a Claude chat (no Python, APIs, or env vars). Builds a quantitative edge score from line value, power ratings (SP+/FPI), injury/trench grades, and market signals (reverse line movement, ticket vs. handle splits), sizes bets with fractional Kelly, and logs every pick so confidence calibration improves over time. Use for a quick manual spot-check of today's pick sheet, or when the user asks for "sharp sheet check," best bets, sharp plays, or edge analysis without wanting to run the full BIM pipeline.
---

# Sharp Sheet Check — lightweight betting edge analysis

## Relationship to Betting Intelligence Machine (BIM) v2.0

This is a **separate, smaller skill**, not a new version of BIM. BIM v2.0 (`betting-intelligence/SKILL.md`) is the full autonomous pipeline — live odds/injury/weather ingestion, hybrid ELO/FPI ratings, a 6-model ML ensemble with Monte Carlo sims, email reports, and scheduled recalibration. This skill does none of that. It's a same-chat, no-infrastructure tool for when you want a fast, disciplined read on today's slate using web search and a single transparent scoring formula — nothing to install, no API keys. Run BIM for the full pipeline; run this for a quick gut-check or when BIM isn't available.

## Purpose and honest framing

This skill finds **long-run expected-value edges**, not guaranteed winners. No model — this one included — can predict a single football game's outcome with certainty; the goal is to be *better calibrated than the market* often enough to show a real edge over a large sample, and to make that edge measurable instead of a vibe. Every output should read like a disciplined analyst's work, not a tout's promise. Never claim a pick is "guaranteed," "can't lose," or similar.

**Responsible-use note (keep this in every full run):** this is probabilistic analysis, not financial or gambling advice. Bet only discretionary funds, follow the gambling laws of your jurisdiction, and treat suggested unit sizes as a ceiling, not a target. If betting stops being fun or starts to feel compulsive, the National Council on Problem Gambling (1-800-GAMBLER) is a good resource.

---

## Step 1 — Initialization menu

When this skill is invoked, do not run the full analysis immediately unless the user's own message already answers the questions below (e.g., "give me the NFL 12pm CST slate" skips straight to Step 2 with no menu). Otherwise present:

---
### 🏈 Sharp Sports Analytics Engine
1. **Sport:** NCAAF or NFL
2. **Kickoff window (CST):**
   - NCAAF: 11:00 a.m. / 2:30 p.m. / 6:30 p.m. / all remaining games today
   - NFL: 8:30 a.m. / 12:00 p.m. / 3:05 p.m. / 3:25 p.m. / all remaining games today
3. **Bankroll unit size** (optional): dollar value of one "unit" for sizing suggestions. If skipped, express everything in units only (0.5u–3u scale).
---

Filter the active slate to the selection, then proceed.

## Step 2 — Performance-log check-in (do this before analyzing games)

If the user has provided or attached a performance log (see `performance_log_template.csv` schema below) or pasted historical results, read it before producing new picks:

1. Group past picks by `confidence_tier` and compute actual hit rate and average `clv_points` (closing line value — the points gained or lost versus the closing line, the single most reliable long-run skill indicator, more reliable than win/loss over small samples).
2. Compare actual hit rate per tier against that tier's assumed win probability (Step 4 table). If a tier has **20+ logged picks** and its real hit rate is **5+ percentage points off** its assumed probability, say so explicitly and adjust this session's thresholds accordingly (e.g., "Strong Play has hit 48% over the last 27 picks against an assumed ~55% — tightening the Strong Play threshold this session and leaning on Max Play only").
3. If average CLV is consistently negative even when win rate looks fine, flag it — it usually means lines are being bet too late or a source is lagging the market.
4. If no log exists yet, say so in one line and proceed with the default calibration — don't block the analysis waiting for history that doesn't exist.

This is what makes the skill improve with use instead of repeating the same static instructions every session.

## Step 3 — Research protocol

**No extrapolation. No invented numbers.** If a source has no usable data for a specific game, write "not available from [source]" rather than filling the gap. Report a **Data Completeness** count per game (e.g., "9/14 sources returned usable data") — treat this as an honesty signal, not a failure.

Run real searches (web_search / web_fetch, or connected tools if available) against as many of these as return verifiable data. Suggested query patterns are in brackets:

| Category | Sources | Query pattern |
|---|---|---|
| Market consensus & line shopping | Covers.com, VSiN, BetMGM, FanDuel, DraftKings | `"[Team A] vs [Team B] odds line" [date]` |
| Sharp/steam signals | Circa Sports, Action Network (ticket % vs. handle %), Don Best / Sports Insights | `"[Team A] [Team B] reverse line movement sharp money"` |
| Predictive power ratings | ESPN SP+, ESPN FPI, CFB Winning Edge / FEI, SportsLine simulations | `"[Team] SP+ rating" / "[Team] FPI"` |
| Efficiency & pace | TeamRankings (pace, red zone, drive stats), Warren Sharp / Sharp Football (EPA/play, explosive rate) | `"[Team] EPA per play" / "[Team] red zone efficiency"` |
| Trenches & injuries | PFF (OL/DL grades), Phil Steele / Inside Injuries (depth charts) | `"[Team] injury report week [X] [year]" / "[Team] offensive line PFF grade"` |

Scale the number of searches to the slate size — a 10-game slate reasonably needs 20–40 targeted searches, not one generic query per game.

## Step 4 — Quantitative edge model

Compute an **Edge Score (0–100)** per game from five weighted components, each normalized to 0–1 before weighting:

```
Edge Score = 30·LineValue + 25·PowerRating + 20·TrenchInjury + 15·MarketSignal + 10·Situational
```

- **LineValue** — how many points better the pick-sheet number is than the no-vig market consensus. Use the approximate football point-to-win-probability curve below (illustrative, not precise — recalibrate from the log over time) to convert the point edge into a probability shift:

  | Point edge | ~Win-prob shift | Note |
  |---|---|---|
  | 1 pt | ~2% | |
  | 2 pts | ~4% | |
  | 3 pts | ~6–9% | key number — value jumps near 3 |
  | 3.5–4 pts | ~9–11% | |
  | 6–7 pts | ~14–16% | key number — value jumps near 7 |
  | 10+ pts | ~20%+ | rare; double-check for data error before trusting |

  NCAAF has fatter outcome tails than NFL (more blowouts, less parity) — treat the same point edge as *less* informative in NCAAF and weight PowerRating/TrenchInjury relatively higher for that sport.

- **PowerRating** — normalized gap between SP+/FPI composite for the two teams, home-field adjusted.
- **TrenchInjury** — PFF OL/DL grade differential, discounted for confirmed starter injuries (a true starter-caliber injury at a line position should materially move this score; a questionable-tag skill player should move it much less).
- **MarketSignal** — reverse line movement or a steam move (line moves toward the side getting fewer tickets) is a strong positive signal; the line moving *with* the public ticket % with no sharp-side divergence is neutral.
- **Situational** — rest/travel, short week, revenge game, divisional familiarity, weather for totals. Keep this the smallest weight; it's real but easy to over-weight into confirmation bias.

**Confidence tiers** (defaults — recalibrate from the log per Step 2):

| Edge Score | Tier | Assumed win prob (default) | Suggested sizing |
|---|---|---|---|
| 80–100 | Max Play | ~60% | 2–3u |
| 65–79 | Strong Play | ~56% | 1–1.5u |
| 50–64 | Lean | ~53% | 0.5–1u |
| <50 | No Play | — | Pass |

## Step 5 — Bet sizing (fractional Kelly)

For each recommended play, show the sizing math, not just the unit number:

```
b = decimal odds − 1
p = tier's assumed (or log-calibrated) win probability
q = 1 − p
Full Kelly f* = (b·p − q) / b
Recommended = 0.25 × f*  (quarter-Kelly, for variance control)
```

Cap any single recommendation at 3% of bankroll regardless of what Kelly outputs — full and even half-Kelly sizing is too aggressive for the uncertainty in a football win-probability estimate. State the unit size both as a fraction of bankroll and, if the user gave a unit value in Step 1, as a dollar amount.

## Step 6 — Parlay logic

Only propose a parlay when legs are **genuinely uncorrelated or positively correlated through a shared driver** (e.g., a team favorite covering and the game going under, both driven by a dominant run-heavy game script) — never combine legs just because both scored well individually. State the combined implied probability and why the correlation (or lack of it) makes the combination reasonable.

## Required output format, per game

```
Matchup: [Team A at Team B]  |  Kickoff: [time CST]
Data Completeness: [n]/14 sources returned usable data

Line: Pick sheet [X] vs. market consensus [Y]  →  LineValue component: [+/- pts, ~prob shift]
Power Rating: SP+/FPI gap [value]  →  component contribution
Injury/Trench: [confirmed injuries, PFF OL/DL gap]  →  component contribution
Market Signal: [RLM / steam / ticket-handle split, or "no signal"]  →  component contribution
Situational: [rest/travel/weather/revenge, or "neutral"]

Edge Score: [0-100]  →  Tier: [Max Play / Strong Play / Lean / No Play]
Estimated win probability: [%]  (default tier value, or log-calibrated — say which)
Recommendation: [Spread/Total/ML] [side] — Suggested size: [Xu] (Kelly math shown)

Log entry (CSV row — copy into performance_log.csv):
[date],[sport],[matchup],[bet_type],[line],[edge_score],[tier],[est_prob],[units],[book],,,
```

End the full session with:
- A ranked top 5–10 list across the slate (highest Edge Score first).
- Any parlay(s), per Step 6.
- **Session risk check**: total units recommended across all plays, flagged if it exceeds a sane single-day cap (default suggestion: 6–8u/day; ask if the user wants a different cap).
- A one-line reminder to log results (win/loss, closing line) back into the performance log once games finish — that's what powers Step 2 next time.

## Updating the log after results are known

When the user comes back with results, update each row's `result`, `closing_line`, and `clv_points` (closing line ± the line you bet, signed so beating the close is positive). Don't recompute past Edge Scores retroactively — the point of the log is to grade the model's *contemporaneous* calibration, not to hindsight-fit it.

## Logging destination: Signal Desk Ledger (Airtable), not a separate system

This skill's picks log into the **same** "Signal Desk Ledger" table that the Signal Desk model (`signal-desk/MODEL.md` + `LEDGER.md`) already uses — as additional columns on the same per-game rows, not a competing table. Signal Desk's own fields (Home FPI, Away FPI, HFA, Model Home Margin, Vegas Implied Home Margin, Edge, Confidence Tier) are untouched; this skill only writes to its own prefixed fields so the two models stay comparable side by side without colliding:

| This skill's field (Airtable) | Maps to |
|---|---|
| Sharp-Sheet Edge Score | `edge_score` |
| Sharp-Sheet Tier | `confidence_tier` |
| Sharp-Sheet Est. Win Prob % | `estimated_win_prob` |
| Sharp-Sheet Suggested Units | `suggested_units` |
| Sharp-Sheet Sportsbook | `sportsbook` |
| Sharp-Sheet Closing Line | `closing_line` |
| Sharp-Sheet CLV Points | `clv_points` |
| Sharp-Sheet Data Completeness | e.g. "9/14" |

If Airtable access is available in the session, create/update the row for that `Game`/`Date` (reuse the existing row if Signal Desk already logged that game; otherwise create one) with these fields. If Airtable isn't available, fall back to appending a row to `performance_log_template.csv` locally and sync it later — don't block the analysis on it.

## See also

`performance_log_template.csv` — local fallback schema, same fields as the table above. Whichever destination is used, keep one running log rather than starting fresh each session, or the calibration loop in Step 2 has nothing to learn from.
