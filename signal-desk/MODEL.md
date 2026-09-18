# Model
engine: model_home_margin = home_fpi - away_fpi + HFA
HFA: NCAAF 2.5, NFL 2.0, neutral 0
Watch threshold: |edge| >= 3
Ensemble weight: 0 (BIM spec unfitted)
Unit plays: disabled until one regular-season week is graded
Changelog 2026-09-18: no parameter change. FPI refresh from ESPN NFL/NCAAF FPI pages after TNF and Pitt final. Market lines from scoresandodds. Neutral: ASU-KU Wembley would use HFA 0 if both FPI used for a watch. No fitting. No neural net.
