# Signal Desk Model

Engine: model_home_margin = home_fpi - away_fpi + HFA
- NCAAF HFA = 2.5
- NFL HFA = 2.0
- Neutral HFA = 0
- Only if BOTH teams have published ESPN FPI
- Watch if |edge| >= 3 vs market spread (home perspective)
- Ensemble weight = 0 (BIM spec exists, not fitted)
- No unit plays until at least one regular-season week is graded
- NFL preseason weight 0.25

Changelog 2026-09-01:
- No new finalized games since 2026-08-31 run. Latest completed slates remain NCAAF Week 0 FBS (8 games, Aug 29) and NFL preseason Week 3 (16 games, Aug 27-29). Neither enters the 75% ATS ledger.
- Reloaded ESPN NFL FPI (all 32 teams still 0-0-0, trend --). Top five FPI: LAR 5.9, BUF 4.1, SEA 3.6, BAL 3.5, SF 3.0 (LAR +0.3, BUF +0.1 vs 8/31 snapshot; BAL/SF slightly down).
- Reloaded full ESPN NCAAF FPI table (138 FBS teams). Numeric FPI used only when both sides published.
- No coefficients trained. Ensemble weight remains 0. No unit size.
