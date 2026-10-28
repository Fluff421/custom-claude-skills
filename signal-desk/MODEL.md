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

Sample-size cap: until a league/tier has 20 graded picks, suggested units are
capped at 1.0 (Lean stays 0.5). The cap also trims pending auto picks that have
no closing line yet. Override with the `UNIT_CAP` and `UNIT_CAP_SAMPLE_MIN`
environment variables.

Games below 1.0 get no pick. Thresholds and units can be overridden per league
in the Airtable Model Parameters table (`Threshold Lean/Strong/Max`,
`Units Lean/Strong/Max`); none are set today, so the defaults above apply.

## Win probability

```
p = Normal CDF(abs(edge) / sigma)        sigma: NCAAF 14.0, NFL 13.5
p = clamp(p * tier multiplier, 0.50, 0.95)
```

Sigma and tier multipliers come from Model Parameters when present.

## Who writes what

| Script | Schedule (UTC) | Writes |
|---|---|---|
| `espn_sync.py` | :15 every 3 h | ESPN Event ID, ESPN Spread/Total, Line Note, Pulled At, Home/Away FPI, HFA, Neutral Site, NFL Injury Notes |
| `picks.py` | :50 every 3 h | Sharp-Sheet Tier, Est. Win Prob, Suggested Units, Sportsbook, Data Completeness, Recommended Side. Only rows with no tier; manual picks are never overwritten. |
| `close_grade.py` | :12 hourly | Closing line (within 3 h of kickoff), scores, Spread/O-U Result, Grade, CLV, pool legs and tickets, Calibration Log |
| `context_sync.py` | 13:30 daily | Last Result, Streak, Next Opponent, Look-Ahead Note (flag if next opponent is 8+ FPI points stronger) |
| `calibrate.py` | 13:30 daily | Model Parameters only |
| `snapshot.py` | 8:15 AM Central daily | `LEDGER.md`, `data/snapshot.json` (read-only on Airtable) |
| `ops_export.py` | same job | `data/graded_picks.csv`, `data/ops_status.json`: row-level ledger health and per-workflow health read from run logs (a "success" run with HTTP 402 or all games unmatched is reported as degraded) |

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
