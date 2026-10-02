# Signal Desk model

Updated 2026-10-02. Ensemble weight = 0. BIM ensemble spec in betting-intelligence is not fitted. No neural-net training.

## Margin

model_home_margin = home_fpi - away_fpi + HFA

- NCAAF HFA 2.5
- NFL HFA 2.0
- Neutral site HFA 0 (London IND-WSH)

Watch only if both teams have a published FPI and abs(model_home_margin - market_home_margin) >= 3.
Market home margin is the current home spread with sign flipped when the home team is the dog (home +3.5 implies market home margin -3.5).

No unit size. No locks.
