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

Changelog 2026-08-30:
- Confirmed Week 0 NCAAF FBS (8 games) and NFL preseason Week 3 (16 games) finalized. Neither enters 75% ATS ledger.
- Reloaded ESPN NFL FPI table (all 32 teams, 0-0-0 regular-season records, trend --).
- NCAAF FPI rank order live on ESPN; numeric FPI published in July preseason snapshot for top tier only. Edges computed only where both sides have numbers.
- No coefficients trained. Ensemble weight remains 0. No unit size.
