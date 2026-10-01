# Signal Desk Model
Engine: model_home_margin = home_fpi - away_fpi + HFA
HFA: NCAAF 2.5, NFL 2.0, neutral 0
Watch if |edge| >= 3 vs current market home line (home margin convention).
Only if both teams have published ESPN FPI.
Ensemble weight = 0. No neural-net training. No unit size.
Changelog 2026-10-01: no parameter change. Refreshed ESPN FPI and ScoresAndOdds lines for unplayed NCAAF Week 5 and NFL Week 4. Prior ledger remains n=0; Week 3 NFL finals (through Mon Sep 28) were not backfilled into the ATS ledger because no Signal Desk picks were issued.
