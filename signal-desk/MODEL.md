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

Changelog 2026-09-04:
- NCAAF Week 1 Thursday slate is FINAL (not in progress). Scores logged from ESPN/USA Today/Las Vegas Sun. Friday-Monday Week 1 games are unplayed; do not grade.
- NFL: no regular-season games yet. Week 1 opens Wed Sep 9 (NE @ SEA). Preseason complete; excluded from 75% ledger.
- Reloaded ESPN NFL FPI (all 32 still 0-0-0, trend --). Top five unchanged: LAR 5.9, BUF 4.1, SEA 3.6, BAL 3.5, SF 3.0.
- Reloaded ESPN NCAAF FPI numeric table. Top five unchanged: OSU 28.7, TEX 26.9, ND 25.9, ORE 25.3, UGA 24.8. USC now 1-0 at 14.0 (rk 16). Missouri 1-0 after Thursday.
- |edge|>=3 watches (not unit plays): NFL NYJ @ TEN; NCAAF TOL @ MSU; NCAAF MIA @ STAN.
- No coefficients trained. Ensemble weight remains 0. No unit size.
