# Model
engine: model_home_margin = home_fpi - away_fpi + HFA
HFA: NCAAF 2.5, NFL 2.0, neutral 0
Watch threshold: |edge| >= 3
Ensemble weight: 0 (BIM spec unfitted)
Unit plays: disabled until one regular-season week is graded
Changelog 2026-09-17: no parameter change. FPI refresh pulled post-NFL W1 / NCAAF W2. Neutral-site note: SF-LAR W1 Melbourne used HFA 0 historically for grading if/when plays exist (none issued).
