# Signal Desk Model

Engine: model_home_margin = home_fpi - away_fpi + HFA
- NCAAF HFA = 2.5
- NFL HFA = 2.0
- Neutral HFA = 0
- Only if BOTH teams have published ESPN FPI
- Watch if |edge| >= 3 vs market spread (home perspective)
- Ensemble weight = 0 (BIM spec exists, not fitted)
- No unit plays until at least one regular-season week is graded
- NFL preseason weight 0.25

Changelog 2026-08-29:
- Initialized 2026 season files. No prior 2026 graded log.
- Preseason FPI snapshot loaded from ESPN (0-0 records, trend --).
- No coefficients trained. No neural net.
