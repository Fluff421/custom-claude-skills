# Model
engine: model_home_margin = home_fpi - away_fpi + HFA
HFA: NCAAF 2.5, NFL 2.0, neutral 0
Watch threshold: |edge| >= 3
Ensemble weight: 0 (BIM spec unfitted)
Unit plays: disabled until one regular-season week is graded
Changelog 2026-09-21: no parameter change. ESPN NFL FPI numbers ingested (SF/BUF 5.6 top). Market: scoresandodds NFL W2 leftover MNF + NCAAF W4 openers. FPI table W-L lags some Sunday results. No fitting. No neural net.
