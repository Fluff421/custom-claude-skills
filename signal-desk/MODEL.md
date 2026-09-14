# Signal Desk Model — 2026-09-14

engine: model_home_margin = home_fpi - away_fpi + HFA
HFA: NCAAF 2.5, NFL 2.0, neutral 0
Requirement: BOTH teams published FPI
Watch: |edge| >= 3 vs market spread
Ensemble weight: 0 (BIM spec exists, not fitted)
Unit plays: disabled until at least one regular-season week is graded with issued plays

Changelog 2026-09-14:
- Formula unchanged. Ensemble remains 0. No unit-size enable.
- ESPN NFL FPI (live 9/14 AM, still largely pre-Sunday bake: most W-L still 0-0 except SF 1-0 FPI 5.5 and SEA 1-0 FPI -0.4 / NE 0-1 FPI 1.4 / LAR 0-1 FPI 2.9): SF 5.5; BUF 4.1; BAL 3.4; LAC 3.0; GB 2.9; LAR 2.9; DET 2.6; KC 2.6; PHI 2.1; DAL 2.0; CIN 1.8; HOU 1.8; DEN 1.5; NE 1.4; JAX 1.2; CHI 1.2; TB 0.1; MIN -0.3; IND -0.3; SEA -0.4; PIT -0.6; WSH -1.3; NYG -1.7; NO -2.8; CAR -2.8; ATL -3.3; TEN -4.0; LV -4.6; NYJ -4.7; CLE -5.3; ARI -5.3; MIA -6.1. Unchanged vs 9/13 MODEL.md values.
- ESPN NCAAF FPI post-Week 2 (On3 + ESPN table 9/14): OSU 30.4 rk1 (1-1, +1); TEX 30.1 rk2 (2-0, -1); ND 27.9; UGA 26.6; MIA 25.7; IU 25.3; BAMA 23.2; TAMU 23.1; LSU 22.6; TENN 17.9. Prior 9/13 note had TEX 30.3 / OSU 30.0 / ND 27.0 / MIA 25.9 / UGA 24.9 — FPI now flipped OSU over TEX after the 24-23 Texas win.
- DEN@KC model_home = 2.6 - 1.5 + 2.0 = +3.1 vs market KC -2.5 (S&O). |edge| = 0.6 < 3. Not a watch.
