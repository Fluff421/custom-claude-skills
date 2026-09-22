# Model
engine: model_home_margin = home_fpi - away_fpi + HFA
HFA: NCAAF 2.5, NFL 2.0, neutral 0
Watch threshold: |edge| >= 3
Ensemble weight: 0 (BIM spec unfitted)
Unit plays: disabled until one regular-season week is graded
Changelog 2026-09-22: no parameter change. NFL FPI refreshed (SF 7.1, BUF 5.6, KC 4.5). FPI W-L still lagged MNF at scrape (LAR 0-1 / NYG 1-0 on FPI page) while scores finalized NYG 6 LAR 28. NCAAF FPI top: OSU/TEX 28.1. Market: scoresandodds NFL W3 openers + NCAAF W4. No fitting. No neural net.
