# Signal Desk Model

## Current Engine (as of 2026-10-24)

model_home_margin = home_fpi - away_fpi + HFA

- NCAAF HFA: +2.5
- NFL HFA: +2.0
- Neutral site: 0

Only applied when BOTH teams have published ESPN FPI.

Watch threshold: |edge| >= 3.0 (vs market line, where available)

**No unit plays issued** until at least one regular-season week is graded.

BIM ensemble spec exists in betting-intelligence but is NOT fitted. Ensemble weight = 0.

No neural-net training. No locks.
