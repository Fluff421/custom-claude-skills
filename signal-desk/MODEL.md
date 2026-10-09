# Signal Desk model

Updated 2026-10-09.

## Formula
model_home_margin = home_fpi - away_fpi + HFA

- NCAAF HFA: 2.5
- NFL HFA: 2.0
- Neutral / international: 0

Edge = model_home_margin - market_implied_home_margin.
Watch if abs(edge) >= 3 and both teams have a published ESPN FPI.

## Weights
- FPI residual: 1.0 of the margin model
- BIM ensemble (Fluff421/custom-claude-skills/betting-intelligence): spec exists, not fitted. Ensemble weight = 0.

## Play gate
No unit plays until at least one regular-season week of issued plays is graded. Gate is closed. No unit size.

## Changelog 2026-10-09
- First 2026 snapshot. No coefficient changes. No neural-net training.
- HFA constants unchanged.
- Ensemble weight remains 0.
