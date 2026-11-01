# Data points to add next

Ranked by expected value for accuracy. Each item says how it would be sourced automatically. Update this file when one ships or is ruled out.

| Rank | Data point | Why it matters | Automatic source | Status |
|---|---|---|---|---|
| 1 | Line movement and closing-line tracking across books | Positive CLV is the best early signal that the model finds real value; we only hold one closing spread | OpticOdds connector or ESPN odds history | not built |
| 2 | Opponent-adjusted efficiency (EPA/play, success rate, SP+ style ratings) | FPI is one rating; blending a second independent rating usually beats either alone | Public play-by-play (nflverse for NFL); published SP+ for NCAAF | not built |
| 3 | Totals model (pace, tempo, red-zone rate) and weather on totals | Weather now touches spreads only; wind and cold move totals more | ESPN team stats plus the existing Open-Meteo feed | not built |
| 4 | Turnover luck regression | Teams with extreme turnover margins regress; the model reads results, not luck | ESPN team stats | not built |
| 5 | Special teams and injuries beyond QB (OL, pass rush, CB) with position-specific values learned from results | Injury values are priors; the learner can fit position groups once enough games exist | ESPN depth chart plus existing injury notes | partly built (QB only) |
| 6 | Coaching and situational tendencies (ATS after bye, after loss, as underdog) | Part of the user's stated goal: how each team and coach responds in each situation | Own graded-pick history, per team | needs 2+ seasons of data |
| 7 | Referee crew tendencies (penalty rate, totals) | Small but persistent | Public assignments pages | not built |
| 8 | Public betting percentages and reverse line movement | Context for fading or following the market | Paid or semi-public sources | needs a source decision |
| 9 | Transfer portal and depth-chart turnover for NCAAF | FPI lags roster change early in a season | Official rosters, Grok research feed | partly (Grok feed) |
| 10 | Playoff/ranking motivation and clinched-status for late season | Teams with nothing to play for underperform | Standings plus rules in code | not built |

Rules for adding a data point: build it in shadow mode, store it in `Factor Detail`, let the learner fit a scale, and promote it only after it beats the base model on the scorecard.
