# Signal Desk Model — 2026-09-12

engine: model_home_margin = home_fpi - away_fpi + HFA
HFA: NCAAF 2.5, NFL 2.0, neutral 0
Requirement: BOTH teams published FPI
Watch: |edge| >= 3 vs market spread
Ensemble weight: 0 (BIM spec exists, not fitted)
Unit plays: disabled until at least one regular-season week is graded
NFL preseason weight: 0.25, excluded from 75% ATS ledger

Changelog 2026-09-12:
- No coefficient changes. Ensemble remains 0.
- NFL FPI now shows SF 5.6 (1-0, rk 1, trend +4) after Melbourne; LAR 3.2 (0-1, rk 4); SEA -0.4 (1-0, rk 18, trend -15 vs prior note); NE 1.5 (0-1, rk 13).
- Prior 9/11 MODEL.md listed SEA -0.7 rk 21 trend +18; live ESPN FPI 9/12 is SEA -0.4 rk 18. Numbers moved with Week 1 results; engine formula unchanged.
- NCAAF FPI top: Texas 30.2, Ohio State 30.0, Notre Dame 27.0, Miami 25.7, Georgia 24.9. Friday FBS finals (MIZ-KU, RUT-BC) not fully reflected in every FPI row at scrape time.
- Unit-play gate still closed. No issued plays.
