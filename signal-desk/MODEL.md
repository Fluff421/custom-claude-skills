# Signal Desk model

Updated 2026-10-08.

## Formula
model_home_margin = home_fpi - away_fpi + HFA

- NCAAF HFA: 2.5
- NFL HFA: 2.0
- Neutral site: 0 (NFL London treated as neutral)

Watch if abs(model_home_margin - market_home_spread) >= 3 and both teams have published ESPN FPI.
No unit size. No locks.

## Ensemble
BIM ensemble spec exists under betting-intelligence but is not fitted.
Ensemble weight = 0.

## Changelog 2026-10-08
- First 2026 snapshot.
- No coefficient change. No neural-net training.
- FPI read from ESPN NFL and college FPI pages on 2026-10-08.
- Lines read from scoresandodds; a few NCAAF numbers cross-checked on ESPN scoreboard / Action Network.
