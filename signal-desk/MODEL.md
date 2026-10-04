# Signal Desk model

Updated 2026-10-04.

model_home_margin = home_fpi - away_fpi + HFA
- NCAAF HFA = 2.5
- NFL HFA = 2.0
- Neutral site HFA = 0 (London, Cotton Bowl)

Watch if both teams have published FPI and abs(model_home_margin - market_home_margin) >= 3.
No unit plays until the play threshold is enabled after at least one graded regular-season week.
Ensemble weight = 0. No neural-net training. No locks.

Changelog 2026-10-04:
- Initial live snapshot. ESPN NFL FPI table ingested. NCAAF FPI numeric values taken from On3 restatement of ESPN FPI top 25 after Week 5 (ESPN page team order confirmed; numeric column did not render in the fetch).
- No coefficient changes. No fit.
