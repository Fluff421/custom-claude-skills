# Signal Desk model

Updated 2026-10-06.

## Formula

model_home_margin = home_fpi - away_fpi + HFA

- NCAAF HFA = 2.5
- NFL HFA = 2.0
- Neutral site (including NFL London) HFA = 0

Edge = model_home_margin - market_home_margin, where market_home_margin is the home team's current spread from the home side (favorite negative).

Watch if |edge| >= 3 and both teams have a published ESPN FPI. Missing FPI = no number.

## Weights

- Market/FPI residual above is the only live signal.
- BIM ensemble spec in this repo is not fitted. Ensemble weight = 0.
- No neural-net training. No unit sizing.

## Changelog 2026-10-06

- First live 2026 snapshot after NFL regular-season Week 4 closed (MNF final).
- No coefficient changes. Ensemble remains 0.
- Play threshold remains off.
