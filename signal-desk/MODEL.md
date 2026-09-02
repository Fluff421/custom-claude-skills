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

Changelog 2026-09-02:
- No new finalized games since 2026-09-01 run. Latest completed slates remain NCAAF Week 0 FBS (8 games, Aug 29) and NFL preseason Week 3 (16 games, Aug 27-29). Neither enters the 75% ATS ledger.
- Reloaded ESPN NFL FPI (all 32 teams still 0-0-0, trend --). Top five FPI unchanged vs 9/01 snapshot: LAR 5.9, BUF 4.1, SEA 3.6, BAL 3.5, SF 3.0.
- Reloaded ESPN NCAAF FPI (138 published). Week 0 records now reflected on a few rows (USC 1-0 FPI 13.6 rk 18 trend +5; UVA 1-0 10.4 rk 26 +6; FSU 1-0 8.0 rk 32 +4; UNC 1-0 5.9 rk 39 +3; MEM 1-0 0.0 rk 65 +9; STAN 1-0 -1.2 rk 74 +6; NDSU 1-0 -1.2 rk 75 +25; TCU 0-1 4.8 rk 43 -5; UNLV 0-1 -0.4 rk 67 -9; NCSU 0-1 -1.4 rk 76 -25; SJSU 0-1 -13.9 rk 123 -10).
- No coefficients trained. Ensemble weight remains 0. No unit size.
