# Signal Desk model

model_home_margin = home_fpi - away_fpi + HFA

- NCAAF HFA: 2.5
- NFL HFA: 2.0
- Neutral site: 0 (applied to IND-WSH, London)

Watch if abs(model_home_margin - market_home_margin) >= 3 and both teams have a published ESPN FPI.

No unit plays. No neural-net training. Ensemble weight = 0.

Changelog 2026-10-03: first live snapshot of the 2026 season in this log. No coefficient changes. FPI read from ESPN NFL and college pages. Market numbers from ScoresAndOdds Week 4 NFL / Week 5 NCAAF.
