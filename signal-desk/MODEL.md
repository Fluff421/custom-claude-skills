# Signal Desk Model

Engine: model_home_margin = home_fpi - away_fpi + HFA
- NCAAF HFA = 2.5
- NFL HFA = 2.0
- Neutral HFA = 0
- Only if BOTH teams have published ESPN FPI
- Watch if |edge| >= 3 vs market spread (home perspective)
- Ensemble weight = 0 (BIM spec exists, not fitted)
- No unit plays until at least one regular-season week is graded
- NFL preseason weight 0.25

Changelog 2026-09-05:
- NCAAF Week 1 Saturday slate is UNPLAYED as of 07:35 CDT. Do not grade Saturday games.
- Finals observed on ESPN FPI scoreboard (not issued plays): Miami 45 Stanford 6; Oklahoma 51 UTEP 0; USC 42 San Jose State 26; USC 39 Fresno State 0.
- NFL: no regular-season games yet. Week 1 opens Wed Sep 9 (NE @ SEA). Preseason complete; excluded from 75% ledger.
- Reloaded ESPN NFL FPI (all 32 still 0-0-0, trend --). Top five unchanged: LAR 5.9, BUF 4.1, SEA 3.6, BAL 3.5, SF 3.0.
- Reloaded ESPN NCAAF FPI. Top five unchanged: OSU 28.7, TEX 26.9, ND 25.9, ORE 25.3, UGA 24.8. Miami FPI now to 21.8 after Stanford. Indiana now rk 6 at 23.1. USC 2-0, FPI 17.5 on default table / listed rk 16 on FPI-sorted page depending on view refresh.
- |edge|>=3 watches (not unit plays): NFL NYJ @ TEN only among fully computed NFL board. NCAAF Saturday FBS-FBS pairs computed only where both FPI published; no new |edge|>=3 card forced without both numbers.
- No coefficients trained. Ensemble weight remains 0. No unit size.
