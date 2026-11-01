# Intelligence data

Everything the betting intelligence system learns and reports, kept in the repo so it is used continuously.

- `latest.md` and `data/YYYY-MM-DD.json`: daily report (best bets, recent results with explanations, accuracy, learner state, gaps). Built at 8:17 AM Central by the Snapshot workflow, read-only.
- `learning_log.csv`: one row per league per day of what the learner believes (sigma, market k, factor scales, Brier). The trend shows whether the system is improving.
- `splash_picks_log.csv` and `splash_picks/`: the user's Splash picks compared with the model, written by the manual Splash-compare workflow, graded in the daily report when games finish.
- `ROADMAP.md`: data points to add next.

All picks are paper picks. Nothing here writes Splash fields or past results.
