# Signal Desk Model

Updated: 2026-09-15

engine: model_home_margin = home_fpi - away_fpi + HFA
HFA_NCAAF = 2.5
HFA_NFL = 2.0
HFA_neutral = 0
watch_threshold: |edge| >= 3.0 vs market home spread
require published FPI for BOTH teams
ensemble_weight = 0
unit_plays = disabled until first graded regular-season week of issued plays

Changelog 2026-09-15:
- First live 2026 regular-season snapshot after NFL Week 1 final (KC 31 DEN 10, Mon 9/14).
- NCAAF Week 2 complete; Week 3 unplayed.
- ESPN NFL FPI ingested with numeric ratings.
- ESPN NCAAF FPI rank order ingested; numeric FPI only captured for ranks 1-11 on scrape (OSU 30.4 through OU 17.8). No CFB watch issued where away or home FPI missing.
- No parameter fit. No BIM ensemble.
