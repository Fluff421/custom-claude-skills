# Signal Desk Model

This file describes what the code on `main` actually does. If a script changes,
update this file in the same PR. Last reviewed: 2026-10-28 (after PR #10).

## Margin and edge (`picks.py`)

```
model_home_margin = Home FPI - Away FPI + HFA
edge              = model_home_margin - Vegas Implied Home Margin   (Splash line)
```

- HFA: NCAAF 2.5, NFL 2.0, neutral site 0 (set by `espn_sync.py` from ESPN's
  `neutralSite` flag). If HFA is blank, `picks.py` falls back to 2.5 / 2.0.
- A pick is made only when both teams have FPI and the Splash line is entered.
- Positive edge picks the home side; negative edge picks the away side.
- Spreads only. The engine does not generate totals or moneyline picks.
- Ensemble weight for BIM = 0 (BIM not fitted).

## Tiers

| Tier | abs(edge) | Default units |
|---|---|---|
| Lean | >= 1.0 | 0.5 |
| Strong Play | >= 2.5 | 1.5 |
| Max Play | >= 4.0 | 3.0 |

Units are earned with closing-line value, not edge size (owner-approved 2026-11-02). FPI-only spread edges have
not held up against closing lines (see `intelligence/validation/sigma_walk_forward.md`), so a tier gets its full
units only when its own picks have beaten the close. `calibrate.py` runs `clv_learning.unit_gate` each day for
every league and tier, using graded picks that have Sharp-Sheet CLV Points:

| Status | Rule | Units |
|---|---|---|
| earned | 20+ picks and mean CLV minus 1 standard error > 0 | the tier's full units |
| not earning | 20+ picks and mean CLV <= 0 | capped at 0.5 |
| unproven | anything else | capped at 1.0 (`UNIT_CAP`), so Lean stays 0.5 |

The status is stored in `intelligence/learning_params.json` (`clv.<league>.gate`), and each change is logged in
`learning_log.csv`. The cap also trims pending auto picks that have no closing line yet. On 2026-11-01 every tier
was unproven. The best was NCAAF Strong, at +1.36 over 11 picks; NCAAF Lean was +0.06 over 33 (SE 0.27) and NCAAF
Max −0.27 over 11.

### Predicted CLV: moving before the market (shadow)

The aim is to price what the market has not priced yet: injuries, quarterback news, rest, travel, look-ahead,
revenge and weather. If those factors carry information, the line should move toward our side before the close.
`clv_learning.fit` learns how far, per league:

    predicted CLV = b_edge * FPI edge toward our side + b_inj * injury points toward our side
                    + sum of b_j * situational points toward our side (look-ahead, rest, travel, revenge, weather)

- **Priors.** The prior for b_edge is past seasons' open-to-close movement toward FPI (`data/history`): NCAAF
  0.083 and NFL 0.20 per point. Its prior SD equals its mean, because ESPN's saved projection is from game day
  and so overstates it. Each factor beta starts at 0 with SD 0.3 points per point.
- **Gates.** The model is fitted only on 30+ graded picks with CLV, and a factor only with 10 non-zero games.
  Below those, it uses the edge prior alone. On the first fit, NCAAF learned b_edge 0.037 from 47 picks: FPI edges
  moved the Splash-to-close line much less than history suggested. NFL has 6 picks and uses the prior.
- **CLV tiers.** Predicted CLV of 0.25 or more is Lean, 0.5 Strong and 1.0 Max. These cut-offs are priors.
- **Logging.** Every new pick records its prediction in Sharp-Sheet Data Completeness (`pCLV +0.31 (CLV tier Lean,
  shadow)`). It is also appended once to `intelligence/markets/clv_shadow.csv`, which is append-only and
  committed by the picks workflow.
- **Forward check.** Each day, `calibrate.py` scores the first logged prediction for each pick against its
  realized CLV.
- **Promotion.** CLV tiers replace edge tiers only with `CLV_TIER_MODE=live` and a forward check that passes. That
  needs 30+ picks and a positive correlation whose 90% lower bound is above 0, plus owner approval. Until then,
  edge sets the tier and CLV sets the units.

Games below 1.0 get no pick. Thresholds and units can be overridden per league
in the Airtable Model Parameters table (`Threshold Lean/Strong/Max`,
`Units Lean/Strong/Max`); none are set today, so the defaults above apply.

## Win probability

```
p = Normal CDF(abs(edge) / sigma)        sigma: learned, prior NCAAF 15.0, NFL 12.5 (see Learned sigma)
p = clamp(p * tier multiplier, 0.50, 0.95)
```

Sigma and tier multipliers come from Model Parameters when present.

### Learned sigma (since 2026-11-02, owner-approved)

All engines now use one sigma. `picks.py` (Ledger spread picks) and `markets.py` (spreads, moneylines, teasers,
alternate lines) both read Model Parameters `Sigma`. A stored value outside the approved range (NCAAF 12-18,
NFL 10-15, such as the old 20) is ignored in favor of the prior.

`calibrate.py` learns sigma daily in `sigma_learning.py`:

1. **Base sigma.** It takes the recency-weighted residual SD of (actual margin − line). The data is past seasons'
   closing lines from `data/history` (weight 0.5 per season back) plus every graded Ledger game against its locked
   Splash line. This is shrunk toward the prior (NCAAF 15.0, NFL 12.5) using 100 pseudo-games. Each run moves it
   at most 0.5, except that a value outside the range is reset. The first estimate is NCAAF 14.94 (n_eff 2,378)
   and NFL 12.42 (n_eff 679).
2. **Context multipliers.** Some games carry more uncertainty: injury-heavy games (3+ combined injury points),
   quarterback uncertainty (QB listed or starter feed), bad weather (severity ≥ 0.5) and big spreads (>14). Each
   segment gets its own multiplier: segment SD / base SD, shrunk toward 1.0 (50 pseudo-games) and kept within
   0.85-1.25. It is applied only after 30 games in that segment, which come from the Factor Detail on graded games.
3. **Records.** Results go to Model Parameters `Sigma` and to `intelligence/learning_params.json`, which holds the
   segments. Every move is logged in `learning_log.csv`. Picks that use a multiplier show it in
   Sharp-Sheet Data Completeness, for example `sigma 16.4 (weather x1.09)`.

The old Brier grid search (8-20) was removed. On uninformative edges, it drove sigma to the top of its range.

### Where sigma and k actually come from (verified 2026-11-01)

The 14.0 and 13.5 above are only the code defaults. Three spread-probability paths are live today, and they
don't all use the same sigma:

| Path | Edge used | Sigma used (NCAAF / NFL) |
|---|---|---|
| `picks.py` Ledger spread pick (`Sharp-Sheet Est. Win Prob %`) | factor-adjusted edge × k, because `FACTOR_MODE=live` since 2026-11-01 22:57 UTC. Before that it was the raw edge (model margin minus line), so tiers before and after that time use different edges | Model Parameters `Sigma` (20 / default 13.5) |
| `markets.py` spread, moneyline and teaser | blended margin = line + k × (model − line) | `sigma_margin` default (16.5 / 13.5). `spread_sigma` is computed from Model Parameters but never used |
| Documentation (this file) | raw edge | 14.0 / 13.5 |

**k is a margin blend, not a probability blend.** The calibrator still fits sigma on the raw edge, while live picks are priced on the factor-adjusted edge × k, so the fitted sigma describes a different quantity from the one it prices. `markets.py` uses blended margin = line + k × (model − line).
`picks.py` (live factor mode only) uses edge × k. These two are the same thing. The calibrator fits k by
regressing (actual margin − line) on (model margin − line). NCAAF k = 0.162 is provisional: the raw estimate
is −0.559 ± 0.686 (n = 47), and the stored value is a prior-shrunk number, so it hasn't been validated
out of sample. NFL has no fitted k and uses the 0.3 prior.

**NCAAF sigma = 20 is a grid boundary, not an optimum.** `calibrate.py` searches 8.0 to 20.0. On the 47 graded
NCAAF spread picks, in-sample Brier keeps falling as sigma rises (14 → 0.2757, 20 → 0.2663, 50 → 0.2555,
coin flip → 0.2500). The learner is driving the probabilities toward 50%, which means the raw edge has shown no
predictive value yet. 38 of the 47 picks are from one slate (2026-10-31), so the sample is also highly correlated.

Every prediction from `markets.py` is now also written to `intelligence/markets/predictions_log.csv`. That file is
append-only and records model_version, config_hash, data cutoff, sigma_version, k_version, event_id and an
explicit event_definition, so later analysis can tell which configuration produced each number.

## Factors: injuries and situation (shadow mode, `factors.py`)

The base model above ignores injuries and situation. The market prices them and FPI mostly does not, so
part of an "edge" can be the market knowing something the model does not. `factors.py` measures that gap
without changing any pick:

```
adj_model_home_margin = model_home_margin + inj_adj + situ_adj
adj_edge              = adj_model_home_margin - Vegas Implied Home Margin
```

- Injuries: parsed from `Injury Notes` (ESPN notes for NFL, the injury-pull notes for NCAAF). Each listed
  player counts for spread points = position value x status weight (Out 1.0, Doubtful 0.75, Questionable
  0.25, Probable 0.05). Non-QB entries are discounted (x0.6) because lists mix starters and backups; a
  Covers-only entry older than 10 days is discounted (x0.3). One team's total is capped (NFL 9, NCAAF 8).
  A blank or unparseable note adds nothing and is never treated as healthy (counted as "without a usable note").
- Situation: only the look-ahead flag is used today (0.5 NFL / 1.0 NCAAF points against the flagged team).
  Rest days, short weeks, travel, revenge and weather are not yet inputs. Weather stays log-only.
- The point values are PRIOR ASSUMPTIONS, not measurements.
- Shadow mode (default): `picks.py` writes `Inj Adj (Home Pts)`, `Situ Adj (Home Pts)`, `Adj Model Home Margin`,
  `Adj Edge`, `Factor Detail` (JSON, includes features and weights version) on unplayed, un-closed games. Tiers,
  sides, probabilities and units still come from the base model. Writes need `FACTORS_SHADOW_LIVE=true`
  and the five ledger fields to exist.
- Live mode (`FACTOR_MODE=live`) makes picks use the adjusted edge. Do not enable until the graded
  sample supports it (calibrate.py reports baseline vs adjusted Brier, log loss and CLV; minimum 30 graded
  rows per league with usable injury notes, adjusted model better on out-of-sample margin error). A human
  sets the variable; no job promotes itself.
- Learning: `Factor Scale Injury` / `Factor Scale Situational` in Model Parameters scale the whole group
  (default 1.0). The scales are learned from graded games, shrunk toward 1.0, only above the minimums.

### Factor learning (`factor_learning.py`, called by `calibrate.py`)

Run daily from graded picks with final scores. Everything is gated by 30 graded games (and, for the
scales, 10 games where the factor was non-zero) and reported in the calibrate log even when not applied.

- Market blend `k`: regress (actual margin - line) on (model margin - line). k near 0 means the line
  already contains what the model knows. A weak prior (0.3 +/- 0.3) is combined with the data and clipped to [0, 1].
  In live factor mode the edge is multiplied by k, so a small k removes most picks.
- Factor scales: regress (actual margin - model margin) on the prior injury and situational points, each
  shrunk toward 1.0 (prior sd 0.5), clipped to [0, 1.5].
- Scorecard: margin RMSE and ATS direction for base vs adjusted vs the line on the same games.
  `ready_for_review` only means the adjusted model beat base by 0.25 points of margin error on 30+ games;
  it never switches anything on.
- Outputs go to Model Parameters (`Factor Scorecard`, `Market Blend K`, `Factor Scale Injury`,
  `Factor Scale Situational`) only when `FACTORS_LEARN_LIVE=true` and the fields exist.

### Situational context and starter checks (`situational.py`, filled by `context_sync.py`)

Written daily to the Ledger for upcoming games; read by `factors.py` (shadow by default).

| Field | Source | Prior (spread pts, unvalidated) |
|---|---|---|
| Home/Away Rest Days | ESPN team schedules, Central calendar days since last completed game | bye (12+ days) +0.5 NFL / +0.6 NCAAF; short (5 or fewer) -0.7 NFL / -0.6 NCAAF |
| Travel Note | team home state (most common home-venue state) to venue state, state centroids | 1000+ mi -0.3, 2000+ mi -0.5, 2+ time zones -0.2 more. Crude on purpose |
| Revenge Note | ESPN schedules this and last season | lost the most recent meeting: +0.3 |
| Weather Note | ESPN event weather | LOG ONLY. Never enters any number until CLV shows a benefit |
| QB Starter Note | Grok feed `qb_starters.csv`, `verified` rows only | OUT replaces any QB injury entry at full QB value, QUESTIONABLE 0.25, PLAYING 0 |

Rest, travel, revenge and look-ahead are summed (`situ_raw`) and share ONE learned scale (`Factor Scale Situational`).
Per-factor parts are stored in `Factor Detail` so a later review can split them.

### Pick in every game

Every game with FPI and a line gets a pick so the learning loop sees all of them. Below the Lean threshold the pick is a
paper tracking pick: tier `No Play`, 0 units, never a bet. If no Splash line exists yet it is priced off the ESPN line and
labelled so; it is re-priced when the Splash line arrives. Max and Strong stay paper with the unit cap in force.

### Per-factor learning, NFL quarterback checks, weather (v3)

- Per-factor scales: `calibrate.py` fits one scale each for injury, look-ahead, rest, travel, revenge and weather in a single
  ridge regression (each shrunk toward 1.0, clipped to [0, 1.5]). A situational factor is only fitted once it was non-zero in 10+
  graded games; until then it keeps its prior (scale 1.0). Stored in Model Parameters: `Factor Scale Injury`, `Factor Scale Situational`
  (= look-ahead, legacy name), `Factor Scale Rest`, `Factor Scale Travel`, `Factor Scale Revenge`, `Factor Scale Weather`.
  A learned scale near 0 switches that factor off; the scorecard reports whether the whole adjusted model beats base.
- NFL quarterback checks (`qb_nfl.py`): ESPN depth chart QB1 plus the injury report. Out/IR = starter_out, Doubtful/Questionable =
  starter_questionable, otherwise starter_playing. A listed BACKUP no longer charges full starter points (before, any listed QB did).
  Rows are labelled `auto_espn`; Grok-verified rows win when both exist. The depth chart can lag a benching.
- Quarterbacks without a starter check (factors v4, 2026-11-02). A row can be priced before the daily context run
  adds its `QB Starter Note`; new weeks' rows are created overnight. NCAAF also has no automatic depth check. In
  that gap, listed QBs used to count 4.0 (NFL) or 3.5 (NCAAF) points each and stacked: on 2026-11-02, two Browns
  third- and fourth-stringers were counted as 8 points and made a Max Play. Now:
  - Only one listed QB per team counts, the one most likely to miss, at backup value: 0.5 × status weight.
  - The pick is capped at Lean, with "QB unverified … capped at Lean" in Sharp-Sheet Data Completeness.
  - Once the starter check arrives, it sets the QB value, and re-pricing applies the full tier.
- Weather (`weather.py`): Open-Meteo forecast at kickoff (worst wind, precipitation chance, snow, cold in the 3 hours after kickoff),
  geocoded from the venue city. Severity 0 to 1 (wind 20+ mph = 1.0, 15+ = 0.6, snow 0.7, rain 60%+ 0.4, cold 0.15 to 0.3); indoor = 0.
  The adjusted margin shrinks toward zero by 10% x severity, capped at 1.5 points. Prior only; the learned weather scale
  governs it. Beyond the 6.5-day forecast window the note is blank (unknown is never treated as clear). Totals are not touched.
  Like every factor it affects picks only when `FACTOR_MODE=live`, which stays a human decision.

## Who writes what

| Script | Schedule (UTC) | Writes |
|---|---|---|
| `espn_sync.py` | :15 every 3 h | ESPN Event ID, ESPN Spread/Total, Line Note, Pulled At, Home/Away FPI, HFA, Neutral Site, NFL Injury Notes |
| `picks.py` | :50 every 3 h | Sharp-Sheet Tier, Est. Win Prob, Suggested Units, Sportsbook, Data Completeness, Recommended Side. Only rows with no tier; manual picks are never overwritten. |
| `close_grade.py` | :12 hourly | Closing line (within 3 h of kickoff), scores, Spread/O-U Result, Grade, CLV, pool legs and tickets, Calibration Log |
| `context_sync.py` | 13:30 daily | Last Result, Streak, Next Opponent, Look-Ahead Note (flag if next opponent is 8+ FPI points stronger) |
| `calibrate.py` | 13:30 daily | Model Parameters only |
| `snapshot.py` | 8:15 AM Central daily | `LEDGER.md`, `data/snapshot.json` (read-only on Airtable) |
| `ops_export.py` | same job | `data/graded_picks.csv`, `data/ops_status.json`: row-level ledger health and per-workflow health read from run logs (a "success" run with HTTP 402 or all games unmatched is reported as degraded); also flags upcoming games where the hand-entered Splash line differs from the ESPN spread by 3 or more points |

`picks.py` and `close_grade.py` are the only scripts allowed to write
Sharp-Sheet or Grade fields. Nothing automated writes the Splash line.
Every script is a dry run unless its `*_LIVE` repo variable is `true`.

## Learning loop (`calibrate.py`)

- Brier score, log loss and a calibration table once a league has 5+ graded
  picks with an estimated probability.
- Tier multiplier = actual win rate / average predicted, clamped to 0.7-1.3,
  only once a tier has 20+ graded picks.
- Sigma is grid-searched (8.0-20.0) to minimize Brier, only with 30+ graded
  picks in the league.

Below those counts the calibrator reports but changes nothing.

## Data sources and known gaps

- FPI: ESPN Core power index JSON (`sports.core.api.espn.com/.../powerindex`),
  matched by ESPN team id (same id as the scoreboard). Done in PR #10,
  2026-10-28. Stored at 1 decimal (`FPI_DECIMALS`). Stale warning when
  `lastUpdated` is older than 72 h; NCAAF `runDateTimeKey` is logged only.
  Teams not in the index (FCS) are reported as FPI missing, never guessed.
  The old HTML page with name matching is a fallback only.
- ESPN JSON feeds (scoreboard, injuries, schedules, power index) are fetched
  directly. WebScraping.AI is used only if a direct fetch fails.
- Lines for comparison: ESPN scoreboard's single embedded provider, not a
  consensus. The bet line is always the Splash line.
- Injuries: NFL automatic (Out / Doubtful / Questionable). NCAAF manual; a
  blank Injury Notes field means no report was copied, not that the team is
  healthy.
- Weather: not used. Log only, until graded CLV shows a benefit.

## Current sample (2026-10-28)

10 graded picks, all NCAAF: Lean 3-5, Strong Play 0-2, Max Play 0 graded.
Every tier is below the 20-pick minimum, so no parameter has been tuned yet.
Judge the model by CLV and calibration before win rate.

## Every bet type (added Nov 2026)

All of this is paper. Spreads and sides, totals, moneylines and parlays are the primary markets; 6-point teasers and other bets (alternate lines) are priced, ranked and tracked every cycle at secondary priority. `markets.py` prices every game in every market (a game with no edge gets tier No Play at 0 units, so it is still tracked and graded).

| Market | Projection | Edge | Tier |
|---|---|---|---|
| Spread | existing model (picks.py, unchanged) | model margin vs line | existing tiers |
| Total | line + k_total x (team-scoring total - line), plus weather, QB and injury points when FACTOR_MODE is live (shadow otherwise) | projected total minus line, in points | NFL 1.5 / 3 / 4.5, NCAAF 2.5 / 4.5 / 6.5 points |
| Moneyline | win probability from the market-blended margin (k from Model Parameters), normal with league sigma | model probability minus the break-even of the DraftKings price | 3 / 6 / 9 points |
| Teaser leg | same blended margin or total, with key-number weighting around 3 and 7 (NFL stronger than NCAAF); legs crossing 3 and 7 are flagged | leg win probability (qualifies at 70% or better) | combination edge |
| Teaser | best 2 and 3 leg combinations from different games | joint probability minus break-even of the reference payout (2 legs -120, 3 legs +160, 4 legs +300; the contest's table decides) | 2 / 5 / 8 points |
| Parlay | Lean-or-better legs across spread, total, moneyline; Gaussian copula with same-game correlation (spread and moneyline on one game are never combined) | joint probability minus break-even of the multiplied leg prices (-110 assumed when no price is known) | 2 / 5 / 8 points |

Numbers above are priors, not results. They are assumptions until each market has 30 graded picks. Moneyline and totals use the line as the starting point because the model has so far shown little information beyond the market (see the market blend in the learning state).

Lines: ESPN's core odds feed (DraftKings pregame) is read every pick cycle and appended to `intelligence/markets/lines_log.csv` only when the number or price changes. When the book's in-progress odds appear, picks for that game freeze. Closing line value for spreads and totals uses the last logged pregame line.

Learning per market: `market_learning.py` writes scorecards (win rate, units, CLV, Brier, calibration, tier and factor performance) and may tune a per-market probability shrink only with 30 or more graded picks for that league and market, a real Brier gain, and at most a 0.15 step per run. Spread settings stay with `calibrate.py` and `factor_learning.py`. Every automatic change, from any of them, is one row in `intelligence/learning_log.csv` (date, league, market, setting, old, new, evidence, sample size, source).

## Splash lines and the locked line

Splash lines move until the pick is made. The ledger's `Vegas Implied Home Margin` and `Over/Under Line` are early-week imports. The line the owner pastes with a pick is the locked line and is the official number. A gap between the two is line movement (or the 6-point adjustment on a teaser), never bad data.

- The log (`intelligence/splash_picks_log.csv`) keeps both: `imported_line` and `locked_line`, with `locked_at`, `movement_for_you` (positive = a better number for the owner), `lead_days` (days from lock to kickoff), and for teaser legs `base_line` and `teased_line`.
- Splash picks are graded only against the locked line. The model is repriced at the locked line and at the imported line; `side_changed` shows when the model would have switched sides.
- Locked lines stay in the repo log. Nothing about Splash is written to Airtable, so no new Ledger field was added for it.
- Timing: the report compares movement and results by how early in the week the pick was locked, with a small-sample warning.
