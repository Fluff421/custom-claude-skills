# Model
engine: model_home_margin = home_fpi - away_fpi + HFA
HFA: NCAAF 2.5, NFL 2.0, neutral 0
Watch threshold: |edge| >= 3
Ensemble weight: 0 (BIM spec unfitted)
Unit plays: disabled until one regular-season week is graded
Changelog 2026-09-19: no parameter change. FPI refresh ESPN NFL/NCAAF FPI. Market lines scoresandodds. Neutral HFA 0 unused on current board (ASU@KU is at Kansas, not Wembley). No fitting. No neural net.
