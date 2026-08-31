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

Changelog 2026-08-31:
- No new finalized games since 2026-08-30 run. NCAAF Week 0 FBS (8) and NFL preseason Week 3 (16) remain the latest completed slates; neither enters the 75% ATS ledger.
- Reloaded ESPN NFL FPI (all 32 teams, 0-0-0, trend --). Reloaded ESPN NCAAF FPI rank table; numeric FPI scraped for ranks 1-11 plus one 0-1 team at -20.8 (rk 138). Edges issued only when both sides have numbers.
- Calendar correction vs prior snapshot: NFL regular-season kickoff is Wed Sep 9 (NE @ SEA), not Sep 10.
- No coefficients trained. Ensemble weight remains 0. No unit size.
