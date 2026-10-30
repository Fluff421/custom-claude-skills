# Grok instructions: NCAAF official availability reports and quarterback starter checks

Version 2026-10-30. Read all of it before your next run. These instructions add to your existing injuries automation (daily 9:30 PM Central, NCAAF Wednesday to Saturday). They do not replace the rules you already follow.

## Why this job exists
A GitHub job now pulls the Covers and DraftEdge NCAAF injury pages every 3 hours (Wednesday to Saturday) and writes the merged result into the ledger. Do not repeat that work. Those pages are secondary sources: Covers is stale (nothing newer than Oct 21 last checked), and DraftEdge skips many teams and does not say whether a listed quarterback is the starter. Your job fills the two gaps the pull cannot:

1. Official conference availability reports, which outrank every aggregator when published.
2. Quarterback starter checks: for every upcoming game, is the quarterback who is listed Out or Questionable actually the starter, or a backup?

## Hard rules (unchanged)
- Repo: `Fluff421/custom-claude-skills`. Branch: `research/grok-feed`. Do not use any other repo.
- Write only under `signal-desk/research/feed/` on that branch. Never touch `main`, scripts, workflows, Airtable, Splash lines, picks or grades.
- Read back every file from GitHub after writing it. Mark a row `verified` only after the read-back matches. Otherwise mark it `unverified` and say so in your report.
- Keep each write small: one file per team or per conference, not one giant file. Large single writes have failed and truncated before.
- Never invent a status. If you cannot find it, write `unknown`. Blank is not healthy and "no report found" is not "healthy".
- Report what you verified separately from what you assumed.
- No secrets in output.

## Inputs you need first
Read these from the repo on `main` (read only):
- `signal-desk/data/snapshot.json` or the ledger export, to get the list of upcoming NCAAF games (home, away, date). If the games list is missing or older than 24 hours, say so and stop; do not guess games.
- `signal-desk/research/SOURCES.md`, which lists the sources and trust levels.

## Task A: official conference availability reports
Schedule: Wednesday through Saturday inside your existing 9:30 PM Central run, plus one extra run Saturday around 10:00 AM Central if you can schedule it.

1. For each conference with an upcoming game (SEC, ACC, Big 12, Big Ten, then others if they publish one), find the official conference availability or player-availability report page. Use the conference's own site or the official social post, not a blog.
2. Open the exact page for this week. Record the URL you actually opened. Do not record a URL you did not open.
3. If the report for this week is not published yet, write one manifest row with `status=not_published_yet` and the time you checked. Do not copy last week's report.
4. If published, for every team playing this week record every player listed, with: team, player, position, official status text exactly as written (for example Out, Doubtful, Questionable, Available), injury or reason if given, report publish time if the page shows it.
5. Write one CSV per conference: `signal-desk/research/feed/availability_ncaaf/<YYYY-MM-DD Central>/<conference>.csv`, plus a `_manifest.csv` listing conference, source URL, time checked (Central), published time shown on the page, row count, `verified` or `unverified`.
6. Same Central date: update the existing folder. New day: new folder.

CSV columns for `<conference>.csv`:
`team,player,pos,status_official,reason,published_at,source_url,checked_at_central,verified`

Important: a team that publishes nothing is `not_reported`, never "healthy". Say which teams had no entry.

## Task B: quarterback starter checks
Schedule: Wednesday through Saturday in the same run.

For each upcoming game, for both teams:

1. Read the quarterback entries from the ledger's `Injury Notes` (the GitHub job writes them, marked `[Injuries AUTO`) and from the official reports from Task A.
2. Identify the team's current starting quarterback from an actual source: the team's official depth chart or game notes, the official game-week release, or a reputable beat reporter or official team post. Name the source URL you opened.
3. Classify each team with exactly one of:
   - `starter_out`: the starter is Out or ruled out by an official source.
   - `starter_questionable`: the starter is Questionable or Doubtful.
   - `starter_playing`: the starter is confirmed available or on the official depth chart with no designation.
   - `backup_listed_only`: the quarterback on the injury list is a backup; the starter is not listed.
   - `unknown`: you could not establish it.
4. Include the name of the starter, the name of the likely replacement if known, and the source URL and its date.
5. Do not use a rumor, a social post from an unverified account, or an aggregator's list as the only basis for `starter_out` or `starter_playing`. If that is all you have, use `unknown` and say what you saw.

Write one CSV per day: `signal-desk/research/feed/availability_ncaaf/<YYYY-MM-DD Central>/qb_starters.csv`.

Columns:
`game,team,side,starter,classification,replacement,evidence_text,source_url,source_date,checked_at_central,verified`

Games to check first (known quarterback flags as of Oct 30, not verified as starters): Ohio State (Sayin), Oregon (Dante Moore), Southern Miss (Hampton), Kansas State (Duff), Clemson (Vizzina), Notre Dame (Hebert), Rutgers (Lonergan), Syracuse (Odom and Nelson), Mississippi State (Taylor), and both Old Dominion quarterbacks (Questionable). Then work through the rest of the upcoming games.

## Conflict handling
When the ledger note and an official source disagree, record both in the CSV rows and add a line in your report: which source said what and when. The newer official source wins; say so but do not edit the ledger.

## Your report (every run)
Keep it short, in this order:
1. What you wrote: folder, files, row counts.
2. Verified (read back from GitHub) versus unverified.
3. Conferences with no published report yet, and the time you checked.
4. Quarterback changes since your last run, with sources.
5. Conflicts between the GitHub job's notes and official sources.
6. Anything you could not do and why.

If a run produces no changes, write no commit and say so.

## What a human or Claude will do with it
You only log facts. A reviewed pull request, written by a person or Claude and merged by the repo owner, decides whether any of this feeds the model or the ledger. Do not propose model changes, pick changes or Splash changes in the feed.

## Stop conditions
Stop and report instead of continuing if: the repo or branch cannot be read, a write fails twice, the games list is stale, or a source page requires a login or is blocked. Do not work around a block.
