# Signal Desk Model — 2026-09-11

engine: model_home_margin = home_fpi - away_fpi + HFA
HFA: NCAAF 2.5, NFL 2.0, neutral 0
Requirement: BOTH teams published FPI
Watch: |edge| >= 3 vs market spread
Ensemble weight: 0 (BIM spec exists, not fitted)
Unit plays: disabled until at least one regular-season week is graded
NFL preseason weight: 0.25, excluded from 75% ATS ledger

Changelog 2026-09-11:
- No coefficient changes. Ensemble remains 0.
- NFL FPI table now reflects 1-0 SEA (-0.7, rank 21, trend +18) and 0-1 NE (+1.5, rank 14). SF and LAR still listed 0-0 at scrape time after Melbourne final.
- NCAAF FPI through Week 1; Week 2 Thursday final (FAMU-MIA) not yet fully reflected in all rows.
- Unit-play gate still closed. No issued plays.
