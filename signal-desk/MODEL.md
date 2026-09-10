# Signal Desk Model — 2026-09-10

engine: model_home_margin = home_fpi - away_fpi + HFA
HFA: NCAAF 2.5, NFL 2.0, neutral 0
Requirement: BOTH teams published FPI
Watch: |edge| >= 3 vs market spread
Ensemble weight: 0 (BIM spec exists, not fitted)
Unit plays: disabled until at least one regular-season week is graded
NFL preseason weight: 0.25, excluded from 75% ATS ledger

Changelog 2026-09-10:
- No coefficient changes. Ensemble remains 0.
- NFL Week 1 opener is final (SEA 13, NE 10). ESPN NFL FPI table still listed all teams 0-0 at scrape time; numeric FPI values used as published.
- NCAAF FPI updated through completed Week 1; Week 2 slate starts tonight (FAMU @ Miami unplayed as of 07:43 CDT).
- Unit-play gate still closed. No issued plays.
