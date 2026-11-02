# Sigma Walk-Forward Validation

Read-only report. No parameter was changed. Candidates were fixed before scoring (see walk_forward.py).
Probability scored: P(model's spread side covers the closing line) = Phi(k x |edge| / sigma). Pushes dropped.

## NCAAF

Games with line, score and FPI projection: 4220. Scored (non-push, non-zero edge): 4170.

| Split | Candidate | n | Log loss | Brier | ECE | ATS hit |
|---|---|---|---|---|---|---|
| selection | C0 | 2639 | 0.6932 | 0.2500 | 0.0050 | 0.517 |
| selection | C1 | 2639 | 0.6936 | 0.2502 | 0.0010 | 0.517 |
| selection | C2 | 2639 | 0.6935 | 0.2502 | 0.0050 | 0.517 |
| selection | C3 | 2639 | 0.6934 | 0.2501 | 0.0123 | 0.517 |
| selection | C4 | 2639 | 0.6932 | 0.2500 | 0.0172 | 0.517 |
| holdout | C0 | 918 | 0.6935 | 0.2502 | 0.0176 | 0.496 |
| holdout | C1 | 918 | 0.6939 | 0.2504 | 0.0202 | 0.496 |
| holdout | C2 | 918 | 0.6938 | 0.2503 | 0.0189 | 0.496 |
| holdout | C3 | 918 | 0.6933 | 0.2501 | 0.0102 | 0.496 |
| holdout | C4 | 918 | 0.6932 | 0.2500 | 0.0044 | 0.496 |
| forward | C0 | 613 | 0.6980 | 0.2524 | 0.0636 | 0.450 |
| forward | C1 | 613 | 0.7005 | 0.2537 | 0.0695 | 0.450 |
| forward | C2 | 613 | 0.6998 | 0.2533 | 0.0679 | 0.450 |
| forward | C3 | 613 | 0.6946 | 0.2507 | 0.0533 | 0.450 |
| forward | C4 | 613 | 0.6932 | 0.2500 | 0.0498 | 0.450 |

Block-bootstrap (by week) 95% interval for mean log-loss difference. Negative favours the first candidate.

| Split | Comparison | Delta | 95% interval |
|---|---|---|---|
| selection | C1_vs_C0 | +0.00037 | -0.00006 to +0.00082 |
| selection | C2_vs_C0 | +0.00029 | -0.00005 to +0.00066 |
| selection | C3_vs_C0 | +0.00017 | -0.00034 to +0.00069 |
| selection | C4_vs_C0 | -0.00006 | -0.00111 to +0.00097 |
| selection | C0_vs_C4 | +0.00006 | -0.00097 to +0.00111 |
| selection | C1_vs_C4 | +0.00043 | -0.00103 to +0.00191 |
| selection | C2_vs_C4 | +0.00034 | -0.00103 to +0.00177 |
| selection | C3_vs_C4 | +0.00022 | -0.00072 to +0.00131 |
| holdout | C1_vs_C0 | +0.00042 | -0.00031 to +0.00108 |
| holdout | C2_vs_C0 | +0.00029 | -0.00024 to +0.00076 |
| holdout | C3_vs_C0 | -0.00018 | -0.00091 to +0.00067 |
| holdout | C4_vs_C0 | -0.00033 | -0.00179 to +0.00134 |
| holdout | C0_vs_C4 | +0.00033 | -0.00134 to +0.00179 |
| holdout | C1_vs_C4 | +0.00075 | -0.00163 to +0.00287 |
| holdout | C2_vs_C4 | +0.00062 | -0.00156 to +0.00254 |
| holdout | C3_vs_C4 | +0.00015 | -0.00068 to +0.00091 |
| forward | C1_vs_C0 | +0.00252 | +0.00106 to +0.00378 |
| forward | C2_vs_C0 | +0.00183 | +0.00076 to +0.00273 |
| forward | C3_vs_C0 | -0.00340 | -0.00502 to -0.00143 |
| forward | C4_vs_C0 | -0.00483 | -0.00739 to -0.00176 |
| forward | C0_vs_C4 | +0.00483 | +0.00176 to +0.00739 |
| forward | C1_vs_C4 | +0.00735 | +0.00283 to +0.01117 |
| forward | C2_vs_C4 | +0.00666 | +0.00253 to +0.01012 |
| forward | C3_vs_C4 | +0.00143 | +0.00021 to +0.00263 |

Model-side CLV if bet at the opening line (points the close moved toward the model side):

- selection: n=1260, mean 0.207 pts, positive 0.4571
- holdout: n=918, mean 0.363 pts, positive 0.4412
- forward: n=613, mean 0.559 pts, positive 0.4976

Leakage audit (FPI projection vs closing line on outright results; ATS beta of FPI edge on closing-line residual):

| Split | n | Outright LL market | Outright LL FPI | ATS beta | SE | Predictor modified after kickoff day |
|---|---|---|---|---|---|---|
| selection | 2677 | 0.4844 | 0.4980 | +0.0805 | 0.0565 | 2675 |
| holdout | 921 | 0.4699 | 0.4787 | -0.0049 | 0.1059 | 920 |
| forward | 622 | 0.4174 | 0.4487 | -0.2293 | 0.0983 | 0 |

Opening-line variant (covers scored against the opening line, the closest proxy to an early Splash lock):

| Split | n | C0 LL | C3 LL | C4 LL | C0 ATS hit | C0 vs C4 (95%) | ATS beta vs open | SE |
|---|---|---|---|---|---|---|---|---|
| selection | 1255 | 0.6926 | 0.6936 | 0.6932 | 0.527 | -0.00056 (-0.00173 to +0.00065) | +0.1534 | 0.0972 |
| holdout | 919 | 0.6924 | 0.6927 | 0.6932 | 0.521 | -0.00073 (-0.00228 to +0.00059) | +0.0322 | 0.1115 |
| forward | 614 | 0.6947 | 0.6943 | 0.6932 | 0.485 | +0.00159 (-0.00161 to +0.00436) | -0.0400 | 0.1026 |

Rating-free sigma check, P(home wins) = Phi(closing line / sigma), log loss:

- selection: best sigma 15 (LL 0.4843); 13.5 0.4854, 14 0.4847, 16.5 0.4856, 20 0.4936
- holdout: best sigma 13.5 (LL 0.4689); 13.5 0.4689, 14 0.4690, 16.5 0.4729, 20 0.4836
- forward: best sigma 13 (LL 0.4163); 13.5 0.4163, 14 0.4167, 16.5 0.4219, 20 0.4343

Residual SD of (actual margin - closing line) by segment:

| Segment | n | SD |
|---|---|---|
| conference:no | 1779 | 15.15 |
| conference:yes | 2441 | 15.1 |
| phase:post | 174 | 15.18 |
| phase:wk1-4 | 1528 | 15.06 |
| phase:wk10+ | 1136 | 15.46 |
| phase:wk5-9 | 1382 | 14.9 |
| season:2022 | 893 | 15.46 |
| season:2023 | 910 | 15.18 |
| season:2024 | 874 | 15.18 |
| season:2025 | 921 | 15.0 |
| season:2026 | 622 | 14.54 |
| spread:7-14 | 1010 | 15.25 |
| spread:<=7 | 1707 | 15.06 |
| spread:>14 | 1503 | 15.11 |

Latest walk-forward parameters: {"C0": {"sigma": 20.0, "k": 0.162}, "C1": {"sigma": 14.0, "k": 0.162}, "C2": {"sigma": 15.121, "k": 0.162}, "C3": {"sigma": 15.121, "k": 0.0099}, "C4": {"sigma": 15.121, "k": 0.0}}

Selected on selection set (lowest log loss): **C4**

Promotion gates:

- 1_leakage_audit: True
- 2_selection_beats_C0_ci_excludes_0: False
- 3_holdout_no_worse_than_C0_and_beats_C4: True
- 4_forward_30_shadow_picks_nonneg_clv: pending: needs predictions_log.csv by config_hash (PR #40)
- 5_one_sigma_source_in_picks_and_markets: pending: picks.py uses Airtable Sigma, markets.py uses sigma_margin
- 6_owner_approval: pending

## NFL

Games with line, score and FPI projection: 1229. Scored (non-push, non-zero edge): 1211.

| Split | Candidate | n | Log loss | Brier | ECE | ATS hit |
|---|---|---|---|---|---|---|
| selection | C0 | 813 | 0.6906 | 0.2488 | 0.0032 | 0.520 |
| selection | C1 | 813 | 0.6906 | 0.2488 | 0.0032 | 0.520 |
| selection | C2 | 813 | 0.6906 | 0.2488 | 0.0065 | 0.520 |
| selection | C3 | 813 | 0.6915 | 0.2492 | 0.0093 | 0.520 |
| selection | C4 | 813 | 0.6932 | 0.2500 | 0.0203 | 0.520 |
| holdout | C0 | 282 | 0.6953 | 0.2511 | 0.0655 | 0.457 |
| holdout | C1 | 282 | 0.6953 | 0.2511 | 0.0655 | 0.457 |
| holdout | C2 | 282 | 0.6955 | 0.2512 | 0.0666 | 0.457 |
| holdout | C3 | 282 | 0.6941 | 0.2505 | 0.0542 | 0.457 |
| holdout | C4 | 282 | 0.6932 | 0.2500 | 0.0426 | 0.457 |
| forward | C0 | 116 | 0.7023 | 0.2545 | 0.0341 | 0.483 |
| forward | C1 | 116 | 0.7023 | 0.2545 | 0.0341 | 0.483 |
| forward | C2 | 116 | 0.7030 | 0.2549 | 0.0353 | 0.483 |
| forward | C3 | 116 | 0.6952 | 0.2510 | 0.0210 | 0.483 |
| forward | C4 | 116 | 0.6932 | 0.2500 | 0.0172 | 0.483 |

Block-bootstrap (by week) 95% interval for mean log-loss difference. Negative favours the first candidate.

| Split | Comparison | Delta | 95% interval |
|---|---|---|---|
| selection | C1_vs_C0 | +0.00000 | +0.00000 to +0.00000 |
| selection | C2_vs_C0 | +0.00000 | -0.00052 to +0.00057 |
| selection | C3_vs_C0 | +0.00080 | -0.00229 to +0.00383 |
| selection | C4_vs_C0 | +0.00250 | -0.00246 to +0.00718 |
| selection | C0_vs_C4 | -0.00250 | -0.00718 to +0.00246 |
| selection | C1_vs_C4 | -0.00250 | -0.00718 to +0.00246 |
| selection | C2_vs_C4 | -0.00250 | -0.00760 to +0.00302 |
| selection | C3_vs_C4 | -0.00170 | -0.00478 to +0.00125 |
| holdout | C1_vs_C0 | +0.00000 | +0.00000 to +0.00000 |
| holdout | C2_vs_C0 | +0.00023 | -0.00007 to +0.00054 |
| holdout | C3_vs_C0 | -0.00123 | -0.00349 to +0.00108 |
| holdout | C4_vs_C0 | -0.00215 | -0.00679 to +0.00232 |
| holdout | C0_vs_C4 | +0.00215 | -0.00232 to +0.00679 |
| holdout | C1_vs_C4 | +0.00215 | -0.00232 to +0.00679 |
| holdout | C2_vs_C4 | +0.00238 | -0.00234 to +0.00732 |
| holdout | C3_vs_C4 | +0.00092 | -0.00136 to +0.00338 |
| forward | C1_vs_C0 | +0.00000 | +0.00000 to +0.00000 |
| forward | C2_vs_C0 | +0.00076 | +0.00018 to +0.00123 |
| forward | C3_vs_C0 | -0.00703 | -0.01215 to -0.00093 |
| forward | C4_vs_C0 | -0.00912 | -0.01555 to -0.00133 |
| forward | C0_vs_C4 | +0.00912 | +0.00133 to +0.01555 |
| forward | C1_vs_C4 | +0.00912 | +0.00133 to +0.01555 |
| forward | C2_vs_C4 | +0.00988 | +0.00152 to +0.01678 |
| forward | C3_vs_C4 | +0.00209 | +0.00026 to +0.00363 |

Model-side CLV if bet at the opening line (points the close moved toward the model side):

- selection: n=272, mean 0.369 pts, positive 0.4118
- holdout: n=282, mean 0.498 pts, positive 0.4362
- forward: n=116, mean 2.026 pts, positive 0.6983

Leakage audit (FPI projection vs closing line on outright results; ATS beta of FPI edge on closing-line residual):

| Split | n | Outright LL market | Outright LL FPI | ATS beta | SE | Predictor modified after kickoff day |
|---|---|---|---|---|---|---|
| selection | 825 | 0.6202 | 0.6337 | +0.2272 | 0.1236 | 765 |
| holdout | 281 | 0.6073 | 0.6382 | -0.5818 | 0.2684 | 281 |
| forward | 119 | 0.6431 | 0.6607 | -0.4919 | 0.4328 | 107 |

Opening-line variant (covers scored against the opening line, the closest proxy to an early Splash lock):

| Split | n | C0 LL | C3 LL | C4 LL | C0 ATS hit | C0 vs C4 (95%) | ATS beta vs open | SE |
|---|---|---|---|---|---|---|---|---|
| selection | 263 | 0.6962 | 0.6933 | 0.6932 | 0.475 | +0.00305 (-0.00228 to +0.00828) | -0.0961 | 0.3327 |
| holdout | 279 | 0.6969 | 0.6932 | 0.6932 | 0.459 | +0.00379 (-0.00150 to +0.00897) | -0.4011 | 0.3157 |
| forward | 120 | 0.6927 | 0.6932 | 0.6932 | 0.525 | -0.00047 (-0.01308 to +0.01075) | +0.2803 | 0.2775 |

Rating-free sigma check, P(home wins) = Phi(closing line / sigma), log loss:

- selection: best sigma 11 (LL 0.6181); 13.5 0.6217, 14 0.6226, 16.5 0.6277, 20 0.6345
- holdout: best sigma 11 (LL 0.6065); 13.5 0.6092, 14 0.6101, 16.5 0.6153, 20 0.6229
- forward: best sigma 13 (LL 0.6429); 13.5 0.6429, 14 0.6431, 16.5 0.6450, 20 0.6488

Residual SD of (actual margin - closing line) by segment:

| Segment | n | SD |
|---|---|---|
| conference:no | 1229 | 12.53 |
| phase:post | 52 | 13.37 |
| phase:wk1-4 | 302 | 13.13 |
| phase:wk10+ | 535 | 12.25 |
| phase:wk5-9 | 340 | 12.32 |
| season:2022 | 284 | 11.6 |
| season:2023 | 285 | 13.77 |
| season:2024 | 258 | 12.64 |
| season:2025 | 282 | 12.24 |
| season:2026 | 120 | 12.06 |
| spread:7-14 | 218 | 12.57 |
| spread:<=7 | 992 | 12.53 |

Latest walk-forward parameters: {"C0": {"sigma": 13.5, "k": 0.3}, "C1": {"sigma": 13.5, "k": 0.3}, "C2": {"sigma": 12.535, "k": 0.3}, "C3": {"sigma": 12.535, "k": 0.0536}, "C4": {"sigma": 12.535, "k": 0.0}}

Selected on selection set (lowest log loss): **C0**

Promotion gates:

- 1_leakage_audit: True
- 2_selection_beats_C0_ci_excludes_0: False
- 3_holdout_no_worse_than_C0_and_beats_C4: False
- 4_forward_30_shadow_picks_nonneg_clv: pending: needs predictions_log.csv by config_hash (PR #40)
- 5_one_sigma_source_in_picks_and_markets: pending: picks.py uses Airtable Sigma, markets.py uses sigma_margin
- 6_owner_approval: pending
