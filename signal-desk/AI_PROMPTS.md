# Signal Desk Reusable Prompts

Version 2026-11-13. Copy the whole block inside the box. Prompts starting with G are for Grok chat, O for any other AI (ChatGPT, Gemini, Claude), P for Perplexity. Splash File 1 and File 2 prompts stay in [CHAT_PROMPTS.md](CHAT_PROMPTS.md), [SPLASH_EXTRACTION_LINES.md](SPLASH_EXTRACTION_LINES.md) and [SPLASH_EXTRACTION_PICKS.md](SPLASH_EXTRACTION_PICKS.md). The owner's manual is [OWNER_GUIDE.md](OWNER_GUIDE.md).

How results come back: Grok writes directly to branch `research/grok-feed`. Other AIs cannot write to the repo; you paste their answer into Perplexity with prompt P4, and Perplexity proposes one exact write for your approval.

## G0. Grok intake questionnaire (run once now, then whenever something looks off)

```text
I run the Signal Desk repo, GitHub Fluff421/custom-claude-skills, folder signal-desk/.
First read from branch main: signal-desk/AI_HANDOFF.md and
signal-desk/research/GROK_INSTRUCTIONS_V3.md. Then answer every question
below from your actual scheduled tasks and your actual run history, not
from memory or intention. If you do not know, say "unknown".

1. List every scheduled task you have that touches Signal Desk. For each:
   exact name, schedule (days and time with time zone), whether it is active
   or paused, the first 3 lines of its instructions, and which instructions
   file version it follows.
2. For each task, every repo path and branch it writes to, and the last
   3 run times with what each wrote (file paths and row counts).
3. Any fault in the last 7 days: failed writes (exact error text), pages you
   could not read, games you skipped, files you looked for that did not exist,
   rows you carried forward from an older file.
4. For the last nightly QB board: games_checked versus games in
   signal-desk/intelligence/markets/picks_latest.json (NFL and NCAAF separately).
5. What would help you most: access, a browser, a different time, fewer
   games per run, clearer instructions, or something else? Be specific.
6. Do you recommend updating your existing tasks to version 3, or deleting
   them and creating new ones? Why?

Then write your full answer to branch research/grok-feed at
signal-desk/research/feed/coordination/grok_status/<today Central YYYY-MM-DD>.md
under the heading "## Intake <HH:MM> CT", read it back, and reply here with
the same answer plus the commit id. Do not change any task yet.
```

## G1. Adopt version 3 for every Grok task

```text
Please update your Signal Desk scheduled tasks to instructions version 3.
Read signal-desk/research/GROK_INSTRUCTIONS_V3.md on main of
Fluff421/custom-claude-skills first.

For each task, replace its instructions with the section 0 lead block of
that file, followed by the task-specific line, and set the schedule:
- Nightly QB board: daily 9:45 PM Central, TASK SECTION 3
- Ops check: daily 8:45 AM Central and 4:45 PM Central, TASK SECTION 4
- Game-window sweep: Thursday to Monday, about 3 hours before the first
  kickoff of the day (default 11:00 AM Central Saturday and Sunday,
  4:30 PM Central Thursday, Friday and Monday), TASK SECTION 5
- Weekly learning note: Monday 10:00 AM Central, TASK SECTION 6
Pause or delete any other Signal Desk task, including duplicates.
If your platform cannot run a task at an exact time, choose the nearest
time and tell me which.

Reply with the final list: name, schedule, active or paused, and the
first 3 lines of each task's instructions. Also append that list to today's
coordination/grok_status file on research/grok-feed, read it back, and
give me the commit id.
```

## G2. One-off research request to Grok

```text
Signal Desk request id REQ-<YYYYMMDD>-<n>. Follow
signal-desk/research/GROK_INSTRUCTIONS_V3.md (main of
Fluff421/custom-claude-skills), section 9.
Request: <paste the "Requests for Grok" item from the daily briefing,
or describe the fact needed, the games and the deadline>.
Write the answer to research/grok-feed at
signal-desk/research/feed/coordination/responses/<YYYY-MM-DD>-<topic>.md
(and to the data folder from AI_HANDOFF.md section 5 if it is QB, weather
or closing-line data), with a source URL and checked time for every fact.
Mark unknown when you cannot verify. Read back, then reply with the files,
row counts and commit id.
```

## G3. Quick Grok status check

```text
Read today's and yesterday's files in signal-desk/research/feed/coordination/grok_status/
on research/grok-feed. Summarize each task run: time, files written, coverage
counts, faults, and what you need from me. Then list any of your Signal Desk
tasks that did not run when scheduled.
```

## O1. QB starters (ChatGPT, Gemini, Claude or any AI with web access)

```text
I need verified quarterback starter status for these games:
<paste games from the Perplexity briefing or picks list: "Away at Home, date">.
For each game and both teams, return one CSV row with exactly these columns:
game,team,side,starter,classification,replacement,evidence_text,source_url,source_date,checked_at_central,verified
Rules: classification is one of starter_out, starter_questionable,
starter_playing, backup_listed_only, unknown. starter_out and starter_playing
need an official source (league or conference injury report, team depth chart,
team release). Copy evidence_text word for word from the source. source_url
must be a page you opened just now. checked_at_central is the time you opened
it. verified is true only for an official source you opened. If you cannot
verify, use unknown. Never guess. Output the CSV only, in one code block,
followed by a list of anything you could not reach.
```

## O2. Injury and availability report

```text
Find the newest official injury or availability report for: <league,
conference or teams>, for games on <dates>.
Return CSV with exactly these columns:
team,player,pos,jersey,status_official,reason,round_title,published_at,source_url,checked_at_central,verified
Use only official league, conference or team sources. Copy statuses exactly.
published_at is the time printed on the report; checked_at_central is when
you opened it. If no report is published yet, return one line:
not_published_yet,<source checked>,<time>. Output the CSV only in one code block.
```

## O3. Weather for outdoor games

```text
For these outdoor games: <games, venues, kickoff times>, return CSV with
exactly these columns:
game,league,kickoff_central,venue,roof,forecast_temp_f,wind_mph,precip_pct,source_url,forecast_issued_at,checked_at_central
Use the National Weather Service point forecast for the stadium location
(weather.gov) first. Give the forecast for kickoff hour. roof is open,
dome or retractable. Unknown values stay blank. Output the CSV only.
```

## O4. Pregame closing lines

```text
For these games: <games with kickoff times>, return the last available
pregame lines from at least two major sportsbooks, captured before kickoff.
CSV columns, exactly:
game,league,market,book,line,price,captured_at_utc,kickoff_utc,source_url
market is spread_home, total or moneyline_home. Use only lines whose capture
time you can show is before kickoff. If you cannot show that, leave the game
out and list it after the CSV. Never estimate.
```

## O5. Research question for the roadmap

```text
I run a free, public-data NFL and NCAAF paper-betting model measured by
closing-line value and calibration. Research this question:
<question, for example "free reliable sources for opponent-adjusted NCAAF
efficiency ratings, updated weekly">.
For each candidate source give: name, URL, what it measures, update
frequency, cost and license terms, whether it has a machine-readable format
(CSV, JSON, API), history depth, and any evidence it predicts against the
closing line. Only include sources you opened. End with your ranked top 3
and the main risk of each.
```

## P1. Picks request (Perplexity)

```text
Signal Desk: give me the paper picks for <tonight | tomorrow | next week>,
all markets, with the readiness gate result, locked-line rules, evidence for
each pick and the current record and calibration.
```

## P2. Ops health check (Perplexity)

```text
Run the Signal Desk ops health check, read-only. Run
python signal-desk/validate_artifacts.py --root signal-desk on a fresh
checkout of main and report ready or not ready with every failing item, its
age and threshold. List each GitHub workflow's scheduled time, newest actual
start time and delay for the last 3 days, and failed runs with the first
error. Report Grok's newest status file and feed coverage. Do not dispatch or
change anything; give me a numbered list of fixes for approval.
```

## P3. Verify Grok's feed (Perplexity)

```text
Signal Desk: verify Grok's feed on branch research/grok-feed, read-only.
For the newest 3 date folders under availability_nfl and availability_ncaaf,
compare qb_starters.csv rows with every game in
intelligence/markets/picks_latest.json (coverage by league), check that each
row has a source URL and a checked time from that night, flag rows copied
from older files, placeholder or header-only CSVs, and paths outside
research/feed. Read today's coordination/grok_status file. Tell me if
Grok is following GROK_INSTRUCTIONS_V3 and draft a G2 request for any gaps.
```

## P4. Load another AI's research into the repo (Perplexity)

```text
Signal Desk: here is research returned by <AI name> for <topic>, prompt
<O1 | O2 | O3 | O4 | O5>. Check it read-only: columns exactly match the
schema in AI_PROMPTS.md, every row has a source URL and checked time, no
invented values, and spot-check at least 3 source URLs yourself.
Then propose one exact write to branch research/grok-feed at
signal-desk/research/feed/external/<YYYY-MM-DD>/<ai>-<topic>.csv
(log only; it does not feed the model). Show repo, branch, path, full
content and commit message, and wait for my approval.
<paste the AI's answer below this line>
```

## P5. Weekly learning review (Perplexity)

```text
Signal Desk weekly learning review, read-only: record and units by league,
market and tier with sample sizes versus gates, CLV, Brier and calibration
buckets, every learning_log change this week and why, my Splash picks versus
the model at the locked line, and Grok's learning note. End with what data
would most improve accuracy next week.
```
