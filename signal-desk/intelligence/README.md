# Intelligence data

Everything the betting intelligence system learns and reports, kept in the repo so it is used continuously.

- `latest.md` and `data/YYYY-MM-DD.json`: daily report (best bets, recent results with explanations, accuracy, learner state, gaps). Built at 8:17 AM Central by the Snapshot workflow, read-only.
- `learning_state.csv`: one row per league per day of what the spread learner believes (sigma, market k, factor scales, Brier). The trend shows whether the system is improving.
- `learning_log.csv`: the change log. One row per automatic change: date, league, market, setting, old, new, evidence, sample size, source.
- `markets/`: `picks_latest.md` and `.json` (every game, every market, teasers and parlays), `picks_log.csv` (every pick, tracked and graded by market), `lines_log.csv` (timestamped lines and prices, appended on change), `scorecards.json` (results and learning by market). `market_params.json` holds per-market settings.
- `splash_picks_log.csv`: the owner's Splash picks for every bet type, with early-week line, locked line, movement and the model repriced at the locked line. Graded against the locked line only.
- `splash_import/`: native owner JSON intake, checksum-bound reviews, durable submission status, accepted receipts, source references and separately executed readiness. Follow [SPLASH_IMPORT.md](../SPLASH_IMPORT.md); the older text/manual route is legacy. An accepted import is not model readiness or a historical pregame prediction.
- `ROADMAP.md`: data points to add next.

All picks are paper picks. Nothing here writes Splash fields or past results.

## Asking for picks
See [ASK_SIGNAL_DESK.md](../ASK_SIGNAL_DESK.md) for a one-line prompt that works in any chat.
