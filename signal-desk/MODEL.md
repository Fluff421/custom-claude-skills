# Signal Desk Model — 2026-09-13

engine: model_home_margin = home_fpi - away_fpi + HFA
HFA: NCAAF 2.5, NFL 2.0, neutral 0
Requirement: BOTH teams published FPI
Watch: |edge| >= 3 vs market spread
Ensemble weight: 0 (BIM spec exists, not fitted)
Unit plays: disabled until at least one regular-season week is graded

Changelog 2026-09-13:
- Formula unchanged. Ensemble remains 0. No unit-size enable.
- ESPN NFL FPI (live 9/13 AM): SF 5.5 rk1 (1-0); BUF 4.1; BAL 3.4; LAC 3.0; GB 2.9; LAR 2.9 rk6 (0-1); DET 2.6; KC 2.6; PHI 2.1; DAL 2.0; CIN 1.8; HOU 1.8; DEN 1.5; NE 1.4 (0-1); JAX 1.2; CHI 1.2; TB 0.1; MIN -0.3; IND -0.3; SEA -0.4 rk20 (1-0, trend +17 listed); PIT -0.6; WSH -1.3; NYG -1.7; NO -2.8; CAR -2.8; ATL -3.3; TEN -4.0; LV -4.6; NYJ -4.7; CLE -5.3; ARI -5.3; MIA -6.1.
- vs 9/12 MODEL: SF 5.6->5.5; LAR 3.2->2.9 rk4->6; SEA listed -0.4 rk20 (was rk18 on 9/12 note). Small post-Melbourne drift only.
- ESPN NCAAF FPI top (pre or mid-update vs Saturday results; table still shows many 1-0 records at scrape): Texas 30.3 rk1, Ohio State 30.0, Notre Dame 27.0, Miami 25.9 (2-0), Georgia 24.9. Saturday upsets (OKST over ORE; MICH over OU; TEX over OSU) may not be fully baked into every FPI row yet.
