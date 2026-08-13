# Betting Intelligence Machine (BIM) v2.0

> **Dependencies:** Python 3.11+, numpy, scipy, scikit-learn, smtplib, dataclasses  
> **External APIs (optional):** Odds API, TheRundown API, OpenWeatherMap, Action Network  
> **Environment Variables:** `BANKROLL` (default 10000), `BIM_EMAIL`, `BIM_EMAIL_PASS`  
> **League Coverage:** NFL + NCAAF  
> **Version:** 2.0 | Updated: August 12, 2026

---

## Purpose
Execute a fully autonomous, mathematically rigorous NFL and NCAAF betting intelligence pipeline — ingesting live odds, injuries, and weather; computing Hybrid ELO/FPI power ratings; running a 6-model ensemble with 50,000-sim Monte Carlo; applying Kelly criterion position sizing; and delivering a structured daily pick report with parlays, CLV tracking, and continuous model recalibration.

---

## When to Use This Skill
- You want data-driven spread, moneyline, and total predictions for any NFL or NCAAF game day
- You need mathematically sound Kelly criterion bet sizing tied to a real bankroll
- You want a 6-model ensemble consensus (XGBoost, LightGBM, Bayesian, Monte Carlo, LSTM, Logistic) rather than a single model's output
- You want Closing Line Value (CLV) tracking and sharp money detection signals
- You want automatic parlay/teaser construction with correlated-probability math
- You want a full daily email intelligence report with tier-ranked plays and risk management triggers
- You want post-game model recalibration and accuracy tracking toward a 75% ATS target
- You are analyzing Ole Miss, any SEC team, or any NFL matchup with live line data available

---

## How It Works

1. **Pull Live Data** — Ingest schedule, lines (DraftKings/FanDuel/BetMGM/Caesars/Pinnacle), line movement, injury reports, weather, sharp money signals, press conferences, and historical ATS/OU trends for every game today
2. **Update ELO + FPI** — Recalculate all team ratings using MOV-adjusted ELO updates and ESPN FPI micro-adjustments from the latest results
3. **Compute Hybrid Power** — `Hybrid = (0.7 × ELO) + (0.4 × FPI_normalized)` where `FPI_normalized = FPI × 20`
4. **Engineer Features** — Calculate EPA per play, success rates, PFF matchup deltas (OL/DL, WR/CB), WPIS injury adjustments, situational factors (rest, travel, divisional, revenge, weather)
5. **Run 6-Model Ensemble** — Execute XGBoost, LightGBM, Bayesian Hierarchical, Monte Carlo (50k sims), LSTM/RNN, and Logistic Regression; combine with dynamic MSE-minimizing weights
6. **Calculate Edges** — No-vig implied probability, model probability, edge %, CLV estimate, and sharp money flags for every bet type
7. **Build Parlays** — Construct optimal 2-leg, 3-leg, 6-pt teaser, and same-game parlays with correlated probability math
8. **Size Positions** — Fractional Kelly (25%) capped at 3% bankroll per bet; tiered sizing by confidence level
9. **Generate Report** — Full structured output per game (power ratings, weather, injuries, predictions, Monte Carlo distribution, model consensus, confidence tier, unit recommendation)
10. **Send Email** — Distribute daily intelligence report with tier-ranked plays, parlay constructions, sharp money alerts, and bankroll status
11. **Monitor Live** — Track in-game score pace vs. total line; flag live bet opportunities on line value or injury impact
12. **Post-Game Update** — Record actual scores, update ELO/FPI for both teams, log CLV, record prediction accuracy
13. **Recalibrate Models** — SHAP feature re-weighting, Platt scaling calibration check, ensemble weight re-optimization via MSE minimization
14. **Confirm Learning** — Output summary of what changed: features up/down weighted, ensemble weight shifts, running accuracy vs. weekly target

---

## Instructions for Claude

When this skill is activated, execute the following in order:

### STEP 1 — Session Initialization
- Print today's date and confirm league(s) in play (NFL preseason/regular/playoffs, NCAAF week number)
- Check bankroll value from `BANKROLL` env var or prompt user to confirm starting bankroll
- Alert if stop-loss flags are active from prior session

### STEP 2 — Team State Setup
For each team playing today, instantiate a `TeamState` with:
- `elo`: start at 1500 for new season; carry forward from last update otherwise
- `fpi`: latest ESPN FPI value (raw, not normalized)
- `games_played`: current season total
- `league`: "NFL" or "NCAAF"
- Compute `hybrid_power = (0.7 × elo) + (0.4 × fpi × 20)`

### STEP 3 — Hybrid ELO/FPI Power Rating Engine
Apply all ELO system parameters:
- K-factor: `K = 20 + (15 × (1 - games_played/17))` for NFL; `/13` for NCAAF
- Home field advantage: +75 ELO points in ELO calculation; +2.5 pts in win probability
- MOV multiplier: `ln(|margin| + 1) × (2.2 / (ELO_diff × 0.001 + 2.2))`
- Post-game update: `New_ELO = Old_ELO + K × MOV_mult × (Result - Expected)`
- Expected: `1 / (1 + 10^((Opp_ELO - Team_ELO)/400))`
- Win probability: `P = Φ((Power_A - Power_B + HFA) / σ)` where σ=25 NFL, σ=28 NCAAF

### STEP 4 — Feature Engineering
Calculate for every game:
- Pass/rush EPA per play (offense and defense separately)
- Success rate (≥40% needed on 1st, ≥60% on 2nd, 100% on 3rd/4th)
- WPIS: `(PFF_grade × 0.4) + (EPA_contribution × 0.35) + (usage_rate × 0.25)`
- Injury WPIS impact: `(WPIS_starter - WPIS_backup) × positional_weight`
  - QB=0.35, WR1=0.15, LT=0.12, RB=0.08, others proportional
- Situational adjustments: rest differential (+2.5 pts for bye), divisional game (-1.5 pts), cold weather QB penalty (<35°F = -0.8), wind total reduction (>15mph = -1.2), precipitation fumble factor (>40% precip = -0.5 to total)

### STEP 5 — 6-Model Ensemble
Run all six models and combine:
