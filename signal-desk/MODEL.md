# Signal Desk Model — 2026-09-08

engine: model_home_margin = home_fpi - away_fpi + HFA
HFA: NCAAF 2.5, NFL 2.0, neutral 0
Requirement: BOTH teams published FPI
Watch: |edge| >= 3 vs market spread
Ensemble weight: 0 (BIM spec exists, not fitted)
Unit plays: disabled until at least one regular-season week is graded
NFL preseason weight: 0.25, excluded from 75% ATS ledger

Changelog 2026-09-08:
- Confirmed NCAAF Week 1 complete (SMU 27, FSU 24 on Sep 7). Not graded — no issued play.
- Refreshed ESPN NFL FPI (pre-Week 1; all 0-0) and NCAAF FPI after Week 1 slate.
- ScoresAndOdds boards: NCAAF Week 2 (starts Thu Sep 10), NFL Week 1 (opens Wed Sep 9). All unplayed.
- No coefficient changes. Ensemble remains 0.
