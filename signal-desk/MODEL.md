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

Changelog 2026-09-03:
- No new finalized games since 2026-09-02 run. Latest completed slates remain NCAAF Week 0 (FBS slate Aug 29 plus Ireland/other Week 0 finals) and NFL preseason Week 3 (16 games, Aug 27-29). Neither enters the 75% ATS ledger.
- NCAAF Week 1 board is open; first kickoffs are tonight (Thu Sep 3). No Week 1 game is in progress or final as of 07:41 CDT. Do not grade tonight.
- Reloaded ESPN NFL FPI (all 32 teams still 0-0-0, trend --). Top five unchanged vs 9/02 snapshot: LAR 5.9, BUF 4.1, SEA 3.6, BAL 3.5, SF 3.0.
- Reloaded ESPN NCAAF FPI ranking order (Ohio State, Texas, Notre Dame, Oregon, Georgia still 1-5). Published numeric FPI confirmed on ESPN table header rows: OSU 28.7, TEX 26.9, ND 25.9, ORE 25.3. Week 0 record rows unchanged from 9/02 changelog (USC 1-0, UVA 1-0, FSU 1-0, UNC 1-0, MEM 1-0, STAN 1-0, NDSU 1-0; TCU/UNLV/NCSU/SJSU 0-1).
- NFL Week 1 FPI vs ScoresandOdds market: NYJ @ TEN is the only |edge|>=3 (model home TEN +2.7 vs market TEN -1.5, edge +4.2). Watch only; not a unit play.
- No coefficients trained. Ensemble weight remains 0. No unit size.
