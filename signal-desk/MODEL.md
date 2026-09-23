# Model
engine: model_home_margin = home_fpi - away_fpi + HFA
HFA: NCAAF 2.5, NFL 2.0, neutral 0
Watch threshold: |edge| >= 3
Ensemble weight: 0 (BIM spec unfitted)
Unit plays: disabled until one regular-season week is graded
Changelog 2026-09-23: no parameter change. NFL FPI refreshed post-W2 (SF 7.4, BUF 5.7, LAR 4.7, KC 4.5; W-L now aligned after MNF). NCAAF FPI top still OSU/TEX 28.1. Market: scoresandodds NFL W3 + NCAAF W4. No fitting. No neural net.
