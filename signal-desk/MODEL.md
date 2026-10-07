# Signal Desk model

model_home_margin = home_fpi - away_fpi + HFA

- NCAAF HFA = 2.5
- NFL HFA = 2.0
- Neutral site HFA = 0

Watch if |model_home_margin - market_home_margin| >= 3 and both teams have published ESPN FPI.

No unit plays until one regular-season week is graded. No locks. Ensemble weight = 0. BIM ensemble spec in betting-intelligence is not fitted.

Changelog 2026-10-07: initialized ledger at zero. Did not import any assumed 2025 week grades.
