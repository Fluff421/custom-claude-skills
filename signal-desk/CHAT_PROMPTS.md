# Signal Desk copy-ready prompts

Use regular Search with GitHub selected. Attach the actual JSON, not the Markdown extraction instructions. The prompts below contain complete requests and compute filenames from the supplied file; there are no date-code or task placeholders to replace.

The current main [intake contract](SPLASH_IMPORT.md) is authoritative. A candidate patch or this file on a branch does not establish deployment; read the current files before using review/status features.

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

After approval use the actual callable file-write action, preferably
single-file push_files with literal content when supported. Do not
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
