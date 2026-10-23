# Signal Desk Model

model_home_margin = home_fpi - away_fpi + HFA
HFA: NCAAF 2.5, NFL 2.0, neutral 0
Watch threshold: |edge| >= 3 points vs market spread (home perspective).
Issued plays: disabled until graded sample exists.
Ensemble: BIM spec exists but not fitted. Weight = 0.
No neural-net training or fake weights.