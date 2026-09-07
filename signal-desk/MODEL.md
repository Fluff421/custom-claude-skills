# Signal Desk Model — 2026-09-07

engine: model_home_margin = home_fpi - away_fpi + HFA
HFA: NCAAF 2.5, NFL 2.0, neutral 0
Requirement: BOTH teams published FPI
Watch: |edge| >= 3 vs market spread
Ensemble weight: 0 (BIM spec exists, not fitted)
Unit plays: disabled until at least one regular-season week is graded
NFL preseason weight: 0.25, excluded from 75% ATS ledger

Changelog 2026-09-07:
- Pulled live ESPN NFL FPI (pre-Week 1 ratings) and ScoresAndOdds Week 1 board.
- NCAAF FPI ranking table live; SMU@FSU not graded (unplayed).
- No coefficient changes. Ensemble remains 0.
