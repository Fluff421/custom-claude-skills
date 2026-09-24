# Model
engine: model_home_margin = home_fpi - away_fpi + HFA
HFA: NCAAF 2.5, NFL 2.0, neutral 0
Watch threshold: |edge| >= 3
Ensemble weight: 0 (BIM spec unfitted)
Unit plays: disabled until one regular-season week is graded
Changelog 2026-09-24: no parameter change. NFL FPI refresh SF 7.3 (was 7.4 on 9/23), BUF 5.7, LAR 4.7, KC 4.5, GB 0.5, ATL -5.2. NCAAF FPI top OSU/TEX 28.1. Market: scoresandodds NFL W3 + NCAAF W4. No fitting. No neural net.
