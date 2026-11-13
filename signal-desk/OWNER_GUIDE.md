# Signal Desk Owner Guide

Version 2026-11-13. This is the owner's single, step-by-step manual for the Signal Desk NFL and NCAAF betting intelligence system in `Fluff421/custom-claude-skills/signal-desk/`. It explains what the system is for, how every piece fits together, when and how to supply Splash data, what each scheduled task does and why it runs when it does, how to read what the system is learning, and how other AI assistants (including Grok) can help.

Companion files:

| File | Use it for |
|---|---|
| [AI_HANDOFF.md](AI_HANDOFF.md) | The one file any other AI reads first: goals, architecture, rules, where to write, how to coordinate |
| [AI_PROMPTS.md](AI_PROMPTS.md) | Copy-ready prompts for Grok, ChatGPT, Gemini, Claude or any other assistant |
| [research/GROK_INSTRUCTIONS_V3.md](research/GROK_INSTRUCTIONS_V3.md) | Grok's standing instructions for every Grok scheduled task |
| [SPLASH_EXTRACTION_LINES.md](SPLASH_EXTRACTION_LINES.md) | File 1 extraction prompt (Splash lines) |
| [SPLASH_EXTRACTION_PICKS.md](SPLASH_EXTRACTION_PICKS.md) | File 2 extraction prompt (your Splash picks) |
| [CHAT_PROMPTS.md](CHAT_PROMPTS.md) | Prompts that submit File 1 or File 2 into the repo through regular Perplexity Search |
| [SPLASH_IMPORT.md](SPLASH_IMPORT.md) | The authoritative intake contract (validation rules) |
| [MODEL.md](MODEL.md) | How the model computes margins, probabilities, tiers and learning |
| [RELIABILITY.md](RELIABILITY.md) | The readiness gate and freshness thresholds |
| [ASK_SIGNAL_DESK.md](ASK_SIGNAL_DESK.md) | One-line prompt for picks from any chat |

---

## 1. The goal in plain words

Signal Desk is a continuously learning paper-betting system for NFL and NCAAF. It puts a pick on every game in every market (spread, total, moneyline, 6-point teasers, parlays, alternate lines), grades every pick, measures how well its probabilities match reality, and slowly tunes itself only when enough evidence exists.

- **Success is measured by:** positive closing-line value (CLV: getting a better number than where the line closes) and good calibration (when it says 60%, it wins about 60% of the time). It is not a promised hit rate.
- **Everything is a paper pick.** Picks stay paper until a tier has at least 20 graded picks, the league has at least 30, data health has been clean for three days, CLV is positive and calibration is reasonable.
- **You are graded on your Splash line.** The early-week imported line and the line you locked can differ; that gap is line movement, never bad data. The locked line is the official number.
- **Minimal cost.** Heavy lifting runs free on GitHub Actions and public ESPN data. Airtable holds the Ledger. Paid AI runs are kept to a few scheduled Perplexity tasks; routine uploads go through regular Perplexity Search (cheaper than Computer); Grok does research on its own schedule at no added Perplexity cost.

## 2. The parts and who does what

| Part | What it is | What it does | Cost |
|---|---|---|---|
| GitHub repo `Fluff421/custom-claude-skills` (`signal-desk/`) | Code, data files, reports | Single source of truth for picks, grades, learning and reports | Free |
| GitHub Actions workflows | Scheduled Python jobs | Pull ESPN lines and ratings, make picks, grade games, learn, write reports | Free tier |
| Airtable base `appSfcG682952AQAv` | The Ledger (one row per game) plus Model Parameters and Calibration Log | Live database the workflows read and write | Existing plan |
| Perplexity scheduled tasks (Computer) | Daily briefing, weekly picks, weekly Splash reminder, on-demand tasks | Read everything, check readiness, explain it to you; read-only | Perplexity credits per run |
| Perplexity regular Search with GitHub selected | Chat | The approved route for submitting File 1 and File 2 into the repo | Low |
| Gemini (in your browser) | Extraction helper | Turns the open Splash page into File 1 or File 2 JSON | Free |
| Grok scheduled tasks | Research partner | Official QB starters, injury availability, ops checks, weekly learning note, written to branch `research/grok-feed` | Your Grok plan |

Data flow in one line: ESPN and official sources, plus your Splash files, go into the Ledger and the repo; GitHub workflows turn them into picks, grades and learning; Perplexity and Grok read the results and report back to you.

```
Splash board --(Gemini File 1)--> regular Search --> repo inbox --> splash-json-inbox --> Splash line history + repricing
Your Splash picks --(Gemini File 2)--> regular Search --> repo inbox --> splash-json-inbox --> owner-vs-model log
ESPN (lines, FPI, scores, injuries) --> ESPN Sync / Seed Ledger / Injury Pull --> Airtable Ledger
Grok QB research --> research/grok-feed --> Context & Calibrate (verified QB rows only) --> Ledger
Ledger --> Pick Engine (all markets) --> Close & Grade --> Context & Calibrate (learning) --> Snapshot (daily report)
Repo files --> Briefing Readiness + Perplexity daily briefing --> you
```

## 3. Your weekly rhythm (all times Central)

| When | What happens | What you do |
|---|---|---|
| Daily 6:13 AM | Context & Calibrate: situational context, verified Grok QB rows, learning | Nothing |
| Daily 7:47 AM | Snapshot: daily report, ops health, Splash repricing | Nothing |
| Daily 8:23 AM | Briefing Readiness check | Nothing |
| Daily 8:30 AM | Perplexity daily intelligence briefing arrives | Read it. If it opens with NOT READY, no current recommendations are released that day |
| Every 3 hours | ESPN Sync, Seed Ledger, Pick Engine | Nothing |
| Hourly | Close & Grade grades finished games | Nothing |
| Monday 9:00 AM | Perplexity weekly Splash reminder: which games still need lines | Do File 1 sometime this week (section 4) |
| Monday through Thursday | NFL and NCAAF Splash boards fill in | Best window for your weekly File 1 once both leagues' games for the week are posted |
| Any time after you lock picks | | Do File 2 Pending within 12 hours (section 5) |
| Saturday night or Sunday | | Optional: File 2 Completed within 24 hours to audit settled tickets |
| Sunday 6:00 PM | Perplexity weekly picks for Monday night through next Sunday | Read it; verify every pick against your Splash line before locking |
| Nightly about 9:45 PM | Grok QB starter board | Nothing, unless Grok reports a fault |

Important current issue (verified November 13, 2026): GitHub has been starting the scheduled morning jobs about 4 to 10 hours late and skipping many others (section 7.4). Until that is fixed, the 8:30 AM briefing usually runs before the day's report exists and opens with NOT READY. That is the system being honest, not a broken briefing.

## 4. File 1: Splash lines (once a week, your choice of day)

**What it is.** A JSON capture of the Splash contest board: every remaining game's spread, total and moneyline as Splash shows them, with the capture time. It lets the model reprice every game at your actual Splash numbers and track line movement.

**Policy.** One File 1 per week is required (168-hour freshness window). Extra captures later in the week are optional and only add line-movement observations; they never overwrite the original. A midweek capture may intentionally include only games that have not kicked off; already-played games are not missing coverage. Older than 4 hours is a visible warning on prices, never a failure by itself.

**When.** Best after the Monday 9 AM reminder, once the week's NFL and NCAAF games are posted on Splash (usually Monday to Wednesday). Capture and submit within 4 hours if you can; the hard limit is 24 hours between capture and submission.

**Steps.**

1. On your computer, open the Splash contest board for the week. Load every league tab and every page; click any show-more buttons so every game is visible.
2. Open Gemini in the same browser (the side panel that can read the open page).
3. Copy the full prompt from [SPLASH_EXTRACTION_LINES.md](SPLASH_EXTRACTION_LINES.md) (the text block under Owner steps) and paste it into Gemini.
4. Gemini returns one compact JSON. Copy all of it. Save it as a text file named after its `date_code` (for example `SPL-L-20261111-2043.json`) as your own backup.
5. Open regular Perplexity Search (not Computer). Before the first message, select GitHub as a source.
6. Paste the prompt "Prepare a complete literal source" from [CHAT_PROMPTS.md](CHAT_PROMPTS.md) and send it.
7. In the next message, paste the complete JSON alone and send it. Keep each message under about 40,000 characters; File 1 from the current extractor is compact enough.
8. Search shows you the exact repo, branch `main`, file path under `signal-desk/intelligence/splash_import/inbox/`, the full content and the commit message. Read the public-repo warning. Approve that one write only if it matches.
9. After the commit, ask Search to verify (prompt "Check an existing submission" in CHAT_PROMPTS.md). Success means a committed status `accepted`, a receipt, matching checksums, the expected row count and `airtable_writes: 0`.
10. If it is rejected, do not resend the same file. Ask Search for the first rejection reason and, if needed, a checksum-bound owner review (prompt "Prepare a recovery review"). Common fix: confirming that a smaller midweek board intentionally contains only remaining games.

Alternative route: you can paste File 1 into a Perplexity Computer thread (as on November 11). It works, but costs more credits. Regular Search is the routine path.

What happens next automatically: `splash-json-inbox` validates and archives the raw file, appends line history to `intelligence/splash_lines_log.csv`, and the Splash pick-time check reprices every game at your Splash line after the next Snapshot (`intelligence/splash_pricecheck/latest.md`).

## 5. File 2: your Splash picks (whenever you have made picks)

**What it is.** A JSON capture of your own Splash tickets (singles, parlays, teasers) at the line you locked. It lets the system compare you with the model at the locked line and grade both fairly.

**When.**

- **Pending (page_type pending):** after you lock picks, within 12 hours (best within 4).
- **Completed (page_type completed):** once a week or after a big slate, covering at least the last 7 days, within 24 hours of capture.
- File 2 does not need a new File 1 first if the games already exist in the Ledger or in an accepted File 1.

**Steps.**

1. Open Splash, go to Pending Picks (or Completed Picks). Expand every ticket and every leg.
2. Open Gemini, paste the full prompt from [SPLASH_EXTRACTION_PICKS.md](SPLASH_EXTRACTION_PICKS.md), and copy the JSON it returns. Save a backup named after its `date_code` (for example `SPL-P-...` or `SPL-C-...`).
3. In regular Perplexity Search with GitHub selected, send "Prepare a complete literal source" from CHAT_PROMPTS.md, then paste the JSON alone in the next message.
4. Review and approve the one exact write. The repo is public: contest links, entry names, stakes and payouts become visible. Remove nothing from the JSON; decide before approving.
5. Verify with "Check an existing submission".
6. For the readable comparison, press Run now on the Perplexity task "Signal Desk: Splash picks vs model (run on demand)". It reads the accepted result and explains, leg by leg, where you matched or went against the model and what the model saw.

## 6. How Perplexity Computer works with your repo

- **Read-only by default.** Every scheduled Perplexity task clones current `main` read-only, reads Airtable read-only and never dispatches or modifies workflows.
- **Readiness gate.** Before releasing current recommendations, a task runs `python signal-desk/validate_artifacts.py --root signal-desk` on a fresh checkout. Any failure means the answer opens with NOT READY, lists each stale or missing item with its age and threshold, and shows only labelled historical analysis. The production Briefing Readiness run is supporting evidence, never a substitute.
- **Writes only with your approval.** Repairs or documentation changes happen on a branch with a pull request. You approve the exact repo, branch, path and content first; you merge the PR yourself; you change repository variables yourself.
- **Live factor mode.** `FACTOR_MODE=live` (verified November 13) means injury and situational factor adjustments do drive picks. Other live switches (`MARKETS_LIVE`, `MARKET_LEARN_LIVE`, `FACTORS_LEARN_LIVE`, `CLOSE_GRADE_LIVE` and others) are all `true`.
- **What Perplexity reads.** Daily report `intelligence/latest.md` and `latest.json`, markets board `intelligence/markets/picks_latest.json`, grades `markets/picks_log.csv`, scorecards, learning logs, Splash logs, ops status, Grok's feed branch, and the Ledger.

## 7. Every scheduled task

### 7.1 Perplexity scheduled tasks (verified November 13, 2026)

| Task | ID | Schedule (Central) | State | What it does with the repo | Why this time |
|---|---|---|---|---|---|
| Signal Desk daily intelligence briefing (8:30 AM Central) | `7d7639b8-db78-4f6c-941f-581bf17d0721` | Daily 8:30 AM | Active | Read-only: runs the readiness gate, reads every report, learning and Splash file and the Ledger, writes you a ten-section briefing | Seven minutes after Briefing Readiness (8:23), after Context (6:13) and Snapshot (7:47), before your day starts |
| Signal Desk weekly picks (Sunday evening) | `9571d4dc-d864-4276-982e-0a4e1ac5fb1a` | Sunday 6:00 PM | Active | Read-only: readiness gate, then every pick Monday night through next Sunday | After Sunday's early and late NFL games settle, before the new week |
| Signal Desk: weekly Splash spreads request | `0beca3da-f5fa-4b5a-986d-f5bf7698c425` | Monday 9:00 AM | Active | Read-only: lists the next eight days of games missing lines, reminds you about File 1 | After weekend grading, when new week boards appear |
| Signal Desk: Splash picks vs model (run on demand) | `aea703e2-c24b-4251-9ef1-a6956f28c596` | Paused; press Run now | On demand | Read-only: reviews File 2 and explains you versus the model at the locked line | Run after each File 2 submission |
| Signal Desk picks on demand (press Run now) | `5e099cdd-3ee0-426f-bf79-bcda576019a4` | Paused; press Run now | On demand | Read-only: readiness gate, then picks for the next 7 days | Any time you want picks now |
| Signal Desk probability read-back | `3a249642-8910-436c-bdaf-9dcb24340c94` | Finished (hidden) | Completed | One-time check of PR #49 repricing | Done; nothing to do |
| Check snapshot commit and Grok ops report | `0b400ffb-c19d-4e69-ac55-6b27136318bc` | One-time Oct 29 | Finished | One-time first check of Grok's ops report | Done; nothing to do |

### 7.2 Changes made to Perplexity tasks on November 13, 2026

- **Weekly picks and on-demand picks:** now run the same readiness gate as the daily briefing, so no task releases picks the briefing would withhold. Both now ask for File 1 only when the newest capture is missing or older than 168 hours, use the locked line as official, and report the live factor mode instead of assuming it.
- **Splash picks vs model:** rewritten for the current native JSON intake. It no longer dispatches the legacy text workflows; it reviews File 2 read-only, points you to the regular-Search submission, and explains the comparison after acceptance.
- **Daily briefing:** keeps all ten sections and every rule. Added: read this guide and AI_HANDOFF.md, add a Grok feed line and producer start-time line to System health, and add a Requests for Grok list to the data-gaps section. No writes authorized.
- **Weekly Splash reminder:** now points you to this guide and reminds you only when the weekly capture is missing or beyond 168 hours.
- No schedule times were changed. The late-GitHub problem (7.4) needs your decision first.

### 7.3 GitHub Actions workflows (`.github/workflows/`)

Times are Central Standard Time; the jobs pick the right UTC slot across daylight saving.

| Workflow | Intended schedule | Reads | Writes | Purpose |
|---|---|---|---|---|
| Seed Ledger | :17 every 3 hours | ESPN schedules | New Game rows in the Ledger (six structural fields) | Makes sure every upcoming NFL and FBS game exists |
| ESPN Sync | :27 every 3 hours | ESPN scoreboard, odds, FPI, NFL injuries | Ledger ESPN fields, `data/source_heartbeats.json` | Lines, ratings and NFL injuries |
| Pick Engine | :47 every 3 hours, and right after Context or Injury Pull succeeds | Ledger, factors, Splash history | Ledger pick fields, `intelligence/markets/*` | Picks in every market, teasers, parlays, repricing |
| Close & Grade | :37 hourly | ESPN finals and closing lines | Ledger results, grades, CLV, Calibration Log, `markets/picks_log.csv` | Grades every finished game |
| NCAAF Injury Pull | Every 3 hours Wed to Sat; 6:33 AM Sun to Tue | Covers, Kickoff Status (DraftEdge fallback) | Ledger Injury Notes | NCAAF availability |
| Context & Calibrate | 6:13 AM daily | Ledger, ESPN schedules, Grok verified QB rows | Ledger context fields, Model Parameters, `learning_log.csv`, `learning_state.csv`, `market_params.json` | Situational factors and all learning |
| Snapshot | 7:47 AM daily, and after Context | Ledger, repo files | `intelligence/latest.md`, `latest.json`, `data/YYYY-MM-DD.json`, `LEDGER.md`, `data/ops_status.json`, `graded_picks.csv` | The daily report and ops health |
| Splash pick-time check | After each Snapshot, or manual | Splash line history | `intelligence/splash_pricecheck/` | Reprices every game at your newest Splash line |
| Briefing Readiness | 8:23 AM daily | Repo files | A run artifact only | Independent readiness check |
| Splash JSON inbox | When an inbox file is committed, and after Close & Grade | `splash_import/inbox/`, `reviews/` | `splash_import/status/`, `receipts/`, Splash logs | Validates and records File 1 and File 2 |
| Splash line history, Splash picks vs model, Splash picks inbox | Manual or legacy | | | Older text route, kept for history; not the routine path |
| Grade BIM Weekly Board | Every 2 hours Sun, Mon, Thu, Fri, Sat | | | Separate BIM board, not the Signal Desk Ledger |
| Unit tests and offline contracts | On pull requests | Code | Nothing | Code checks only; green tests are not production health |

### 7.4 Known fault: GitHub schedules are late or skipped (verified November 13, 2026)

| Workflow | Expected scheduled runs since Nov 6 | Actually started | Typical delay |
|---|---|---|---|
| Close & Grade | about 182 | 28 | Gaps of 4 to 8 hours |
| ESPN Sync | about 61 | 23 | |
| Pick Engine | about 61 | 23 (plus chained runs) | |
| Seed Ledger | about 61 | 7 | |
| Context & Calibrate (6:13 AM) | | started between 10:48 AM and 4:27 PM | About 4.5 to 10 hours late |
| Snapshot (7:47 AM) | | started between 11:51 AM and 5:10 PM | About 4 to 9.5 hours late |
| Briefing Readiness (8:23 AM) | | started between 12:04 PM and 5:29 PM | About 3.5 to 9 hours late |

GitHub does not guarantee scheduled start times and drops runs under load. The code and thresholds are fine; the clock is the problem. Options, cheapest first:

1. **Free external trigger (recommended, $0).** A free scheduler such as cron-job.org calls GitHub's workflow-dispatch API for Context & Calibrate at 6:13 AM (Snapshot and Pick Engine then follow automatically) and Close & Grade at 7:30 AM (optionally hourly on game days). You create a fine-grained GitHub token limited to this one repository with Actions read and write, and paste it only into the scheduler. Request body: `{"ref":"main","inputs":{"live":"true"}}` to `https://api.github.com/repos/Fluff421/custom-claude-skills/actions/workflows/context-calibrate.yml/dispatches` (and `close-grade.yml`).
2. **Perplexity dispatcher task.** A small separate task at about 6:05 AM that only dispatches those workflows and confirms they started. Reliable, but costs credits every day. The daily briefing itself stays read-only.
3. **Move the briefing later** (for example 5:30 PM). No setup, but grading freshness (under 2 hours) would still fail often because Close & Grade is skipped most hours.

## 8. Grok: what it does now and how we coordinate

### 8.1 What Grok is doing now (observed from its commits on `research/grok-feed`, not yet confirmed by Grok)

| Observed Grok task | Observed time (Central) | Writes to | Notes |
|---|---|---|---|
| Task 1: nightly QB board (NFL and NCAAF) | About 9:43 PM daily | `research/feed/availability_nfl/<date>/` and `availability_ncaaf/<date>/` (`qb_starters.csv`, `_manifest.csv`, `_selfreview.md`) | Feeds the model: Context & Calibrate reads verified rows from the newest three date folders at 6:13 AM |
| Ops check | About 8:42 AM, often an update about 4:45 PM | `research/feed/ops/<date>.md` | Reads ops_status.json and counts graded rows |
| Game-window sweep | Afternoons or evenings on game days | `availability_ncaaf/<date>/` | Pre-kickoff QB recheck for midweek games |
| Weekly learning note | Irregular (Tue 10:45 PM, Thu 8:04 AM); intended Monday 10 AM | `research/feed/ops/<date>-learning.md` | Weekly sample sizes and calibration summary |

### 8.2 Grok faults found on November 13

- NCAAF QB coverage is far below the target: on November 12 Grok checked 2 of an estimated 40+ upcoming NCAAF games; the conference CSVs are placeholders.
- Grok looks for files that do not exist on main (`data/upcoming_games.csv`, `intelligence/injury_history.csv`). The real upcoming-game list is `intelligence/markets/picks_latest.json` (every pending game).
- Grok's ops check called the system "OK" from an ops export that was already many hours old; it must compare `generated_at` with the current time and with the thresholds.
- One ops check failed reading a file path that did not exist (`ops/2026-11-07.md`, your screenshot).
- Some rows were retained from prior runs and re-stamped, which version 2 forbids unless the source was re-opened.
- The learning note runs on irregular days.

### 8.3 Recommendation: tweak, do not start over

Grok's nightly QB board is already wired into the model and working mechanically, and its file layout matches what the code reads. Starting over would risk breaking that link. The plan is to keep Grok's existing tasks, replace their instructions with [research/GROK_INSTRUCTIONS_V3.md](research/GROK_INSTRUCTIONS_V3.md), and add a coordination file. If Grok's answers to the intake questionnaire (AI_PROMPTS.md, prompt G0) show tasks we do not know about, duplicates or writes outside its folder, then cancel and recreate them from version 3.

### 8.4 How Perplexity and Grok talk to each other

- **Grok to Perplexity:** Grok writes `signal-desk/research/feed/coordination/grok_status/<YYYY-MM-DD>.md` on branch `research/grok-feed` at the end of every Grok task (append a section per task). The daily briefing reads it and reports a Grok feed line.
- **Perplexity to Grok:** the daily briefing lists "Requests for Grok" in its data-gaps section. Grok's tasks also derive their own work list each run from the standing requests in [AI_HANDOFF.md](AI_HANDOFF.md) and from current gaps in `picks_latest.json` and `ops_status.json`. No Perplexity task writes to the repo, so you relay any one-off request by pasting prompt G2 from AI_PROMPTS.md into Grok.
- **Feedback loop:** each morning the briefing checks Grok's newest files (coverage, verified counts, faults). Grok's next run reads the briefing's published gaps through the repo files it already reads.

### 8.5 Your steps to set up Grok

1. Paste prompt G0 (intake questionnaire) from [AI_PROMPTS.md](AI_PROMPTS.md) into Grok. Copy Grok's full answer back into this Perplexity conversation.
2. Based on the answer, paste prompt G1 (adopt version 3) into Grok so it updates each of its scheduled tasks to lead with the version 3 header.
3. After Grok's next nightly run, ask Perplexity to verify the feed (prompt P3 in AI_PROMPTS.md).

Target Grok schedule after G1 (Central):

| Grok task | When | Section of GROK_INSTRUCTIONS_V3.md | Why then |
|---|---|---|---|
| Nightly QB board | Daily 9:45 PM | 3 | Lands before Context & Calibrate (6:13 AM) reads the newest three folders |
| Ops check | Daily 8:45 AM, update 4:45 PM | 4 | Right after the 8:30 AM briefing; afternoon update catches late GitHub runs |
| Game-window sweep | Thu to Mon, about 3 hours before the first kickoff | 5 | Late QB news and weather before lines close |
| Weekly learning note | Monday 10:00 AM | 6 | After the weekend's games are graded |

### 8.6 Working with ChatGPT, Gemini, Claude or another AI

1. Pick the matching prompt in [AI_PROMPTS.md](AI_PROMPTS.md): O1 QB starters, O2 injury reports, O3 weather, O4 pregame closing lines, O5 roadmap research.
2. Fill in the games (copy them from the Perplexity briefing or prompt P1 answer) and paste the prompt into the other AI.
3. Copy the AI's full answer and paste it into Perplexity below prompt P4.
4. Perplexity checks the columns and spot-checks sources, then shows one exact write to `research/grok-feed` at `signal-desk/research/feed/external/<date>/<ai>-<topic>.csv`. Approve it only if it matches.
5. These files are logged for review and do not change picks; only Grok's `qb_starters.csv` files feed the model today.

## 9. Reading what the data is telling you

| Term | Plain meaning | Where |
|---|---|---|
| Tier | Max Play, Strong Play, Lean (positive units) and No Play (0 units, tracking only) | `picks_latest.json` |
| Edge | Model number minus the line, in points | Board and briefing |
| Win probability | Model chance the pick wins at that line | Board |
| Brier score | Average squared error of probabilities; 0.25 equals coin-flip guessing; lower is better | `latest.md`, `scorecards.json` |
| Calibration | Do 60% picks win about 60%? Shown by probability buckets | `latest.md` |
| CLV | Points better (positive) or worse than the closing line; the best early sign of real skill | `picks_log.csv` |
| Sigma | How wide the model thinks game outcomes spread around its margin; learned from historical plus Ledger residuals | `learning_state.csv` |
| Market blend k | How much the model leans toward the market; near 0 means the line already contains what the model knows | `learning_state.csv` |
| Factor scales | Learned multipliers for injuries, look-ahead, rest, travel, revenge, weather; 1.00 means unchanged from the prior | `learning_state.csv` |
| Teaser shrink | Pulls teaser-leg probabilities toward 50% when they were overconfident | `learning_log.csv` |
| Gates | 20 graded per tier, 30 per league and market, 30 games with factor records and 10 non-zero per factor; nothing tunes below its gate (base sigma is the exception) | MODEL.md |

Snapshot as of November 13, 2026 (paper, historical): 152 graded primary picks, 76-76, Brier about 0.259 (slightly worse than coin-flip guessing), NFL 30 and NCAAF 122 graded. Market history: spreads 42-44, totals 42-44 (+2.16 units), full teasers 15-9 (+6.10 units), full parlays 3-16. The newest automatic change was the NCAAF teaser-leg shrink moving from 0.70 to 0.55 on 126 outcomes. No tier has passed every promotion gate, so everything stays paper.

How to read the trend: look for CLV staying positive over many picks, Brier drifting below 0.25, and calibration buckets lining up. A hot or cold week under 30 picks is noise.

## 10. Owner checklists

**Daily (2 minutes):** read the 8:30 AM briefing headline and section 7. NOT READY means no current picks that day.

**Weekly:** one File 1 after the Monday reminder; File 2 Pending after you lock picks; read Sunday's weekly picks; optionally File 2 Completed for the past week.

**When something breaks:** ask Perplexity "Run the Signal Desk ops health check" or paste prompt P2 from AI_PROMPTS.md. Never fix by editing generated CSVs or Airtable by hand.

**Decisions only you make:** merging pull requests, changing repository variables, approving any repository write, enabling or disabling live modes, and choosing a fix for the late GitHub schedules.

## 11. Change log

- **2026-11-13:** this guide, AI_HANDOFF.md, AI_PROMPTS.md and GROK_INSTRUCTIONS_V3.md added; ASK_SIGNAL_DESK.md schedule and Grok sections corrected; version 2 Grok instructions marked superseded; other-AI research folder `research/feed/external/` defined (log only); Perplexity weekly picks, on-demand picks, Splash comparison, daily briefing and weekly Splash reminder prompts updated (7.2). Late GitHub schedules documented with options (7.4).

The owner can run the Splash picks comparison (File 2 dump of pending or completed picks) and the weekly Splash spreads request (File 1 line dump) manually at any time. Paper picks only; verify against your Splash line before locking.
