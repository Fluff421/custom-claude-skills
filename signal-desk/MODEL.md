# Signal Desk Model

Updated: 2026-09-27

## Engine
model_home_margin = home_fpi - away_fpi + HFA
- NCAAF HFA = 2.5
- NFL HFA = 2.0
- Neutral = 0
- Require published FPI for BOTH teams.
- Watch if |model - market| >= 3.0
- Ensemble weight = 0

## Changelog 2026-09-27
- Morning refresh after NCAAF Week 4 Saturday finals; NFL Week 3 Sunday still unplayed (07:39 CDT).
- Reloaded ESPN NFL FPI table (SF 7.3 through MIA -8.0) and ScoresAndOdds Week 3 board.
- Neutral-site HFA=0 kept for BAL vs DAL (Maracana / Rio).
- No coefficient refit. Ensemble still 0. No unit plays issued.
- CFB FPI numeric table on espn.com/college-football/fpi was rank-complete; post-Saturday On3 reprint showed UGA 28.3 / ND 27.8 / OSU 27.8 / TEX 26.9 after Saturday results. Engine not used to issue CFB unit plays.

## Changelog 2026-09-26
- Refreshed ESPN FPI and ScoresAndOdds boards morning of NCAAF Week 4 Saturday / NFL Week 3 Sunday slate.
- No coefficient refit. Ensemble still 0. No unit plays issued.
- Neutral-site handling applied to BAL vs DAL (Rio).

## Changelog 2026-09-25
- First live 2026 Signal Desk run in this mailbox.
- Loaded ESPN FPI after NFL TNF (ATL 35, GB 14) and NCAAF Thu (LIB 34, CCU 17).
- GB FPI now -0.9 (1-2); ATL -3.4 (1-2).
- No coefficient refit. No neural net. No unit plays issued.
