# Signal Desk model

Updated 2026-10-05.

model_home_margin = home_fpi - away_fpi + HFA

HFA: NCAAF 2.5, NFL 2.0, neutral 0.

Edge used only when both teams have a published ESPN FPI. Watch if absolute edge >= 3 versus the current market home margin.

BIM ensemble spec exists in this repo under betting-intelligence but is not fitted. Ensemble weight = 0.

No locks. No neural-net training. No unit plays until the play threshold is enabled.
