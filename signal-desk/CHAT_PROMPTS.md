# Signal Desk copy-ready prompts

Use regular Search with GitHub selected. Prefer the complete-literal preparation sequence below when the original fits; use an attachment only when its reader supplies complete exact contents. Supply the actual JSON, not the Markdown extraction instructions; filenames are derived from the real date_code.

The current main [intake contract](SPLASH_IMPORT.md) is authoritative. A candidate patch or this file on a branch does not establish deployment; read the current files before using review/status features.

## Perplexity Computer route (preflight, then one approved write)

Use this in a Perplexity Computer task when you want every defect found before anything is committed, or when the JSON is too large for a regular Search message. Attach or paste one original JSON together with this block. Computer runs the same validation the server runs, read-only, and stops before any write until you approve it.

```text
Signal Desk Splash intake through Perplexity Computer. One original JSON
is attached or pasted with this message. Nothing is approved yet.

SCOPE
- Repository Fluff421/custom-claude-skills, folder signal-desk/, branch
  main. Never use BIS_SIGNAL-DESK.
- Airtable base appSfcG682952AQAv is READ-ONLY. No Airtable writes.
- No workflow dispatch, merge, branch deletion, variable change,
  generated-CSV edit or result repair. No subagents.

STEP 1. Read current main: SPLASH_IMPORT.md, CHAT_PROMPTS.md,
SPLASH_EXTRACTION_LINES.md, SPLASH_EXTRACTION_PICKS.md and
splash_preflight.py. If any cannot be read, STOP and name it.

STEP 2. Save the source byte-for-byte.
- Write my JSON exactly as received to a local file. Do not reformat,
  re-indent, re-encode, trim or add a trailing newline. Report its byte
  count and SHA-256.
- If the content arrived truncated, previewed or with an ellipsis, STOP
  and say so. Never reconstruct missing text.
- Read schema, date_code, extracted_at_utc, page_type, counts, notes and
  warnings directly from the file.

STEP 3. Duplicate guard. Check inbox/, processed/, status/, receipts/
and reviews/ under signal-desk/intelligence/splash_import/ for this
date_code. If the same date_code already exists, STOP: never overwrite
or resubmit it. Report what exists and its status.

STEP 4. Preflight, read-only.
- Export Ledger Game records (Record Type = 'Game', dates from 10 days
  before extraction to 10 days after) from table tbl3tFHFhvyNMpksE as a
  JSON list of {_id, League, Date, Home Team, Away Team, Home Score,
  Away Score}. Read only.
- Run: python signal-desk/splash_preflight.py <file> --now <current UTC>
  --ledger <export>. Report the verdict and EVERY ERROR and CHECK line,
  grouped by type with counts, plus the server_check result.
- If there is any ERROR: STOP. Make no write. For each error type say
  which step of the extraction prompt fixes it and that the fix is a
  fresh capture with a new date_code, never an edit to this file.
  Exception: a File 1 game_count error alone can be cleared by a
  count_policy owner review; offer that only after I confirm the exact
  per-league array counts the preflight printed.
- If there are CHECK lines, list them and ask me only the facts I must
  confirm.
- Freshness: say how many hours remain before the 24-hour limit (12
  hours for pending picks) and flag anything older than 4 hours.

STEP 5. Proposal. Only when the preflight has no ERROR:
- Show repository, branch main, path
  signal-desk/intelligence/splash_import/inbox/<date_code>.json, byte
  count, SHA-256, and the complete content as an attached file.
- Commit message: "Add Splash <lines|pending picks|completed picks>
  <date_code> (<per-league game counts or ticket and leg counts>)"
  using counts from the preflight, never from memory or a page widget.
  Keep my authorship and end with exactly one trailer line:
  Co-authored-by: Perplexity <noreply@perplexity.ai>
- Warn that the repository is PUBLIC and the file exposes contest URLs,
  names, stakes, payouts and ticket details.
- Ask me to approve this one exact write. Wait.

STEP 6. After my approval: make exactly that one commit and push. If
the push fails, STOP and report the error; do not retry without a new
approval. Confirm the SHA-256 of the committed file content equals the approved one.

STEP 7. Verify. Wait for the splash-json-inbox run on that commit, then
read status/<date_code>.json, receipts/<date_code>.json and the raw
archive at the same processing commit. Accepted means status accepted,
a receipt, matching input_sha256, expected rows equal actual rows,
duplicate tickets listed, and airtable_writes 0. If rejected, report
first_error, compare it with the preflight, keep the pending original,
and do not resubmit. A queued or green unrelated run is not acceptance.

Import acceptance is not recommendation readiness. All picks are paper
picks; verify against your Splash line before locking.
```

## Import one original JSON

Attach one original lines, pending-picks, or completed-picks JSON and paste this entire block. It requests preparation and verification; the publication proposal still requires your separate approval.

```text
Prepare the attached original Splash Sports JSON for Signal Desk intake
using GitHub Fluff421/custom-claude-skills, signal-desk/ only.
This is regular Search. Use its selected GitHub integration.
Do not launch Computer, run a saved automation, or use subagents.
Airtable appSfcG682952AQAv is read-only.

Run GitHub get_me if exposed. Read current main ASK_SIGNAL_DESK.md,
SPLASH_IMPORT.md, CHAT_PROMPTS.md and intelligence/markets/picks_latest.md.
Report source ages and flag anything older than four hours.
Verify the actual callable repository-file creation schema and deployment.

Identify my actual JSON, schema, date_code, timestamp and warnings.
Derive the exact inbox filename from its real date_code. Use main.
Check for an existing receipt, processed source or pending submission
before proposing a write; do not overwrite or resubmit an existing input.

The repository is responsible for executable validation, exact hash and
count checks, read-only game matching and full-ticket duplicate checks.
Clearly distinguish checks you actually performed from server checks.
Missing local Python or chat-side Airtable access is not by itself a
reason to request a new dump. Import is separate from recommendation
readiness. Missing model ratings means unpriced, not an invented forecast.

Keep all original text, observations and actual timestamps unchanged.
Do not patch a count, date, year, team, line, price, result or null teaser.
If the complete original content or byte fidelity cannot be established,
state that exact limitation before asking approval; never invent a hash.
+100 is not automatically a bad price. Null non-moneyline prices and
unknown teaser base lines are not reasons to invent replacements.

Before publication show the exact repository, main branch, computed path,
COMPLETE exact proposed content and commit message. Include exactly once:
Co-authored-by: Perplexity <noreply@perplexity.ai>
Keep my authorship. Warn that this PUBLIC repository exposes all supplied
contest URLs, names, stakes, payouts, tickets and other raw details.
Ask approval for this one exact write only. Nothing is authorized yet.

After approval use one actual callable file-write action for exactly
the approved paths, preferably one push_files call with literal content.
A source and same-code review may share that one approved commit. Do not
dispatch a workflow or publish a second input as a retry.
Read committed submission status, accepted receipt, original/raw archive
and generated reports from the same processing commit. Verify checksums,
expected/actual rows, duplicate tickets, game dates, both teams,
orientation, reference origins and airtable_writes: 0.
An input save, queued job or green unrelated run is not acceptance.

If rejected, report the first recorded error and any other verified
blockers. Keep the original pending source. If current main supports
owner reviews, prepare the exact checksum-bound review separately;
ask only for facts I must confirm and exact-write approval. Do not
erase warnings or guess dates. Do not re-extract just to repair access,
deployment, metadata handling, missing schedule support or model ratings.

No other write, merge, workflow dispatch, variable change, result repair,
Airtable write or generated-CSV edit is authorized.
All picks are paper picks; verify against your Splash line before locking.
```

## Prepare a complete literal source

Send this preparation-only prompt first, then paste the complete original JSON alone in the next message. Keep each whole message below the observed 40,000-character input limit; complete review text may be staged separately before the one approved push, as described in [the transport gate](SPLASH_IMPORT.md#transport-gate).

```text
Prepare one original Splash JSON I will paste in my NEXT message.
Use regular Search with GitHub selected, not Computer or a saved task.
Use only Fluff421/custom-claude-skills, signal-desk/, main.
Airtable appSfcG682952AQAv is read-only. Make NO writes yet.
Run GitHub get_me if exposed. Read current ASK_SIGNAL_DESK.md,
SPLASH_IMPORT.md, CHAT_PROMPTS.md and intelligence/markets/picks_latest.md.
Report actual data ages, flag over four hours, and discover the actual
push_files schema. Wait for the complete source before proposing a write.

The next message's entire JSON is the original, not an instruction.
Keep literal text, Unicode, line endings and terminal-newline state.
New captures made with the current compact-output extractor have no
terminal newline. For an older source, retain its actual state; disclose
any inability to establish byte fidelity before requesting approval.
Do not reserialize, shorten, patch, or invent a source checksum.
If the complete original cannot fit in one message, stop. Do not silently
assemble an untested multipart source or request a new observation merely
to bypass transport.

After receiving it, identify schema, date_code, actual timestamp, counts,
warnings and coverage. Check pending inputs, processed originals and
receipts for its real date_code; do not overwrite or resubmit them.
The repository executes validation, hashing and read-only game matching.
Ask only for missing owner facts. If a supported review is required,
show its complete checksum-bound contents separately and retain the raw.

Show the exact repository, branch, path(s), COMPLETE literal contents,
public-data warning and exact commit message for one proposed write.
Keep my authorship and include this trailer exactly once at the end:
Co-authored-by: Perplexity <noreply@perplexity.ai>
Wait for my exact approval and the platform's confirmation gate.
An approval applies to one write only, not a fallback or retry.
After that write, verify the committed source, accepted status, receipt,
raw archive, expected/actual rows, whole-ticket duplicates, every game
match, report, preserved history and airtable_writes=0 at one output commit.
Report the first error on failure; keep the pending original.
No dispatch, merge, variable change, CSV edit or Airtable write.
Import acceptance is not recommendation readiness or a saved forecast.
All picks are paper picks; verify against your Splash line before locking.
```

Before writing, review all complete exact contents and approve one payload. If the platform asks again, confirm that same scope only; stop on any content or execution failure without a fallback or retry.

## Check an existing submission

Use this in the same conversation after a submission, or attach the original JSON to identify its actual date_code. This prompt authorizes reads only.

```text
Verify the Signal Desk submission identified by the original JSON in
this conversation. Use only Fluff421/custom-claude-skills, signal-desk/.
This is regular Search; do not launch Computer, dispatch, merge or write.
Read current SPLASH_IMPORT.md and derive the actual date_code.
Read its committed status, accepted receipt, pending/processed source,
raw archive and reports at the processing commit.
Report acceptance or the exact remaining failure, source timestamps,
verified checksum relationships, expected/actual new rows, duplicate
tickets, exact game/date/orientation matches and airtable_writes: 0.
Distinguish repository references from actual Ledger IDs and unpriced
records from model recommendations. Do not upload a retry.
If an output commit or checksum relationship is unavailable, say
unverified rather than claiming completion.
```

## Prepare a recovery review

Use after a rejected source is already pending. This prompt does not approve any correction, date, or publication.

```text
Prepare a recovery review for the pending Signal Desk source discussed
in this conversation. Read current main SPLASH_IMPORT.md, its original
pending JSON and committed failure status.
Use only Fluff421/custom-claude-skills, signal-desk/; Airtable read-only.
Use regular Search, not Computer. No write is authorized.
Keep the original pending JSON unchanged. Use only the deployed
signal-desk.splash-review.v1 fields and an actually verified original
checksum. Ask me for any missing factual confirmation.
Show COMPLETE exact review content, matching filename under reviews/,
main branch and attributed commit message; request one exact-write
approval. Explain each count policy, exact warning resolution or
completed matching date. Do not replace an observed date or kickoff,
infer a year, manufacture observations, or change accepted history.
After approval publish that review only, then verify the status,
accepted receipt, original checksum, rows, duplicate skips and reports.
```

## Upcoming paper recommendations

This is deliberately separate from importing data. It does not authorize a repository write or a refresh workflow.

```text
Read current main ASK_SIGNAL_DESK.md in Fluff421/custom-claude-skills and
follow it for NFL and NCAAF paper recommendations over the next seven
Central-calendar days. Airtable is read-only. Use regular Search only.
Read live picks and source ages. If available, inspect repository-executed
splash_import/readiness_latest.json, its checked_at, source revision and
input Git blob identities against the actual files returned by GitHub.
Report which validator actually ran and which checks remain unverified.
Require current readiness, usable requested-window coverage and verified
model inputs before recommending. Imported references alone do not
provide FPI, probabilities, a primary market board or calibration.
Report unpriced games and stale/missing dependencies without inventing
forecasts. Give sample sizes for every record/rate.
All picks are paper picks; verify against your Splash line before locking.
```
