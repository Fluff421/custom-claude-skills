# Signal Desk Model

## Engine
model_home_margin = home_fpi - away_fpi + HFA
HFA: NCAAF 2.5, NFL 2.0, neutral 0
Watch if |edge| >= 3

Ensemble weight = 0 (BIM not fitted).

No unit plays until graded regular-season sample exists.

Changelog: Initial 2026 setup. Simple FPI + HFA only.