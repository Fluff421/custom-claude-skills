# MODEL.md

model_home_margin = home_fpi - away_fpi + HFA
HFA: NCAAF 2.5, NFL 2.0, neutral 0.

Only generate watch if both teams have published ESPN FPI and |model - market| >= 3.
No unit plays until at least one full regular-season week is graded.
BIM ensemble not fitted. Weight=0.
