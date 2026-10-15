# Signal Desk Model

## Engine (simple FPI)
model_home_margin = home_fpi - away_fpi + HFA
- NCAAF HFA: 2.5
- NFL HFA: 2.0
- Neutral: 0

Only if BOTH teams have published FPI.
Watch if |model_home_margin - market_home_margin| >= 3.

No unit plays until at least one regular-season week is graded.
NFL preseason weight 0.25, excluded from 75% ATS ledger.
Week 0 FCS/FBS excluded from 75% ledger.

## Ensemble
BIM ensemble spec exists in betting-intelligence but is NOT fitted.
Ensemble weight = 0.

No fake neural-net training. No locks.
