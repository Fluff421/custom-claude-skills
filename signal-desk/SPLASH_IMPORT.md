# Splash Sports imports from regular chat

This is the repository-only import path for the owner's native File 1 lines and File 2 picks JSON; it never writes to Airtable. The implementation was merged in [PR #58](https://github.com/Fluff421/custom-claude-skills/pull/58). Installed code, an active workflow, an available regular-chat write action, valid source data, existing Ledger games, and a successful production receipt are separate checks. Do not describe the importer as merely proposed because an older report says so, or describe an import as complete merely because the code is installed.

## Check chat access before requesting another dump

Do this once in regular Perplexity Search, with GitHub selected before the first message. Do not attach another dump just to check access. [Perplexity's troubleshooting instructions](https://perplexity.ai/help-center/en/articles/2026091803-troubleshooting-the-github-connector) explain source selection and connector sessions.

```text
Use the connected GitHub integration, not web search, for this check.
Do not write anything and do not launch Computer.
For Fluff421/custom-claude-skills, report:
1. Whether this chat actually exposes a callable repository-file creation
   or update action. Identify the action if available. A general GitHub
   connection, repository read, or PR-label action is not proof.
2. The current state of PR 58 and whether main contains
   .github/workflows/splash-json-inbox.yml and signal-desk/splash_import.py.
If the file-write action is unavailable, state that limitation and stop.
Do not ask me for another Splash extraction to fix missing chat tools.
```

The source-selection check is not itself evidence that file writes are supported. [Perplexity's GitHub help](https://www.perplexity.ai/help-center/en/articles/12275669-github-connector-for-enterprise) documents actions generally, not the availability of this particular action in every chat.

## The simple routine

- **Prepare**: Use your existing owner-run extraction to obtain the complete Splash JSON. Do not change counts, dates, lines, or results to make a file pass.
- **Open regular Search**: Before the first message, select GitHub with the paperclip. Typing `@GitHub` alone does not select it, according to [Perplexity's troubleshooting instructions](https://perplexity.ai/help-center/en/articles/2026091803-troubleshooting-the-github-connector).
- **Verify the action once**: Use the access check above before requesting a fresh extraction. Do not perform a write during this check. If the action is missing, report a transport limitation rather than a bad-file diagnosis.
- **Submit**: Attach or paste one raw JSON file, followed by the import prompt below. Review the complete content, target path, branch, public-data warning, and commit message, then approve exactly one file write.
- **Wait for the receipt**: Do not submit another file until this one's output commit is confirmed. The repository automation performs the import; no manual Actions form, compression, or workflow dispatch is needed for this path.

The processing workflow contains no Computer invocation or paid model API call. Regular-chat limits, connector permissions, and repository automation usage still apply; this is not a promise that every surrounding service is free.

## Copy-ready regular-chat prompt

```text
Use only Fluff421/custom-claude-skills, under signal-desk/.
Airtable base appSfcG682952AQAv remains read-only.

I am supplying the owner's original Splash Sports JSON. Do not invent or
change any dates, counts, teams, lines, teaser adjustments, or results.
First verify that you can create one repository file from this regular
chat; if that action is unavailable, say so and do not claim an import.
Do not launch Computer, a Computer task, or a Computer automation.

Read the current main-branch signal-desk/SPLASH_IMPORT.md and importer.
Check live deployment state, not a historical audit's deployment label.
Identify the schema and date_code.
For File 1 use signal-desk.splash-lines.v1.
For File 2 use signal-desk.splash-picks.v1.

Review all independent blockers together before requesting new data.
More than four hours old is a freshness warning, not automatic rejection.
The hard age limit is 24 hours for lines or completed-pick extractions,
and 12 hours for pending-pick extractions. Do not change timestamps.
Count games by league from the actual games array and compare the header.
A count mismatch does not prove a game's league tag is wrong. Ask the
owner's extractor to verify the complete board and compute its header
from the captured entries; do not patch this supplied file.
Use a fresh read-only Ledger query to verify matching if available.
A stale operations summary is not a current Ledger row export. If no
current Ledger access exists, say matching is unverified, not zero.
Missing Ledger games cannot be fixed by resubmitting the same dump,
running the existing sync, or waiting without a schedule-creation route.
Do not create Ledger rows, invent record IDs, or waive matching.

Only after the access, source, freshness, count, and matching checks pass,
prepare exactly:
signal-desk/intelligence/splash_import/inbox/<date_code>.json
on branch main, with the raw JSON unchanged.

Before the write, show the exact path, branch, complete file content,
and proposed commit message. Warn that this public repo exposes raw
contest links, entry names, stakes, payouts, and other supplied details.
Ask for approval for this one write only. Do not use a different path
or silently update an existing submission.

After approval, save that one file. Wait for repository processing.
Confirm the successful processing commit, accepted receipt, raw-file
checksum, new row count, duplicate skips, and exact game/date matches.
Read the generated report. A saved input alone is not import completion.
On rejection or failed processing, report the reason and stop.

This is an import request, not a picks-analysis request. General
read-only analysis instructions do not authorize an import write.
Only my separate approval of the exact file below authorizes that one
GitHub write. No other repository or Airtable write is authorized.
No Airtable writes, variable changes, result patches, or hand-edited CSVs.
All picks are paper picks; verify against your Splash line before locking.
```

For a commit created by the assistant, retain the user's authorship and end the message with `Co-authored-by: Perplexity <noreply@perplexity.ai>` exactly once. Each import is a separate approval; approval of the implementation is not blanket approval to publish later dumps.

## What the new workflow does

- **Accepted inputs**: One newly supplied JSON file per owner-authored push to `main`. Native lines and pending/completed picks use the same inbox.
- **Validation**: Supported schema and exact source; safe date code; timezone-aware extraction timestamp; no unresolved warnings; finite numeric lines; parseable Central kickoff; seasonally correct Central timezone label if supplied; correct spread signs; exact per-league counts and unique games.
- **Freshness**: Lines and completed-pick extractions must be at most 24 hours old; pending-pick extractions at most 12 hours old. Anything older than four hours is flagged even if still within its import limit.
- **Extraction counts**: The owner-run extractor should build the complete `games` array first and compute `game_count` from its actual league tags. Page-wide counters may refer to another tab, filter, or slate; that is a reason to inspect the source, not to reclassify a game or fill in an unseen game. Do not assume the header or array is correct until the owner verifies coverage. A timestamp-only refresh is not a fresh extraction.
- **Count exception**: Only an exact, per-league removal of already-finished games from the same prior slate can justify a smaller board. A previous week finishing cannot excuse unrelated header errors.
- **Matching**: League, Central date within one day, and both teams must identify exactly one existing Ledger row. Exact names take priority; only uniquely identifying short names can resolve. Reversed or uncertain home/away orientation fails validation instead of silently flipping.
- **Picks**: Full-name text conversion, explicit `Parlay:` and `Teaser:` lines, and `teased` suffixes are preserved. A null teased number is never inferred. Duplicate full tickets are skipped; changed source-ticket identities require review. Moneyline price is included in ticket identity.
- **Preservation**: Raw input is archived byte-for-byte with a SHA-256 receipt. Supplied stake, payout, source ticket ID, and reported result stay in the receipt and raw file, not Airtable. Existing generated logs are updated only by the importer.
- **Line history**: The first capture becomes an early snapshot; subsequent captures append movement instead of changing earlier rows. This does not fill blank Ledger fields.
- **Reports**: A lines import produces a movement report and a current-line check. A picks import produces a comparison and an archived full-name text representation in `splash_picks/processed/`.
- **Reconciliation**: A separate derived view grades existing paper legs using their recorded Splash lines and available Ledger scores. It refreshes after a successful Close & Grade run without rewriting immutable capture-status fields or importing owner-reported results as database facts.
- **Visible failures**: Input validation, output-count discrepancies, commit errors, and rebase conflicts fail visibly. A successful local calculation is not the same as a committed production import.

The old text inbox and manual workflows remain available. The new native-JSON route deliberately avoids requiring an intermediate owner-written text file; its text representation is produced after validation.

## Where to read the result

| Result | Repository path |
|---|---|
| Accepted receipt | `signal-desk/intelligence/splash_import/receipts/<date_code>.json` |
| Archived inbox JSON | `signal-desk/intelligence/splash_import/processed/<date_code>.json` |
| Current derived outcomes | `signal-desk/intelligence/splash_import/reconciliation/latest.json` |
| Lines raw input | `signal-desk/intelligence/splash_lines/raw/<date_code>.json` |
| Lines movement report | `signal-desk/intelligence/splash_lines/<date_code>.md` |
| Current-line check | `signal-desk/intelligence/splash_pricecheck/latest.md` and `latest.json` |
| Picks raw input | `signal-desk/intelligence/splash_picks/raw/<date_code>.json` |
| Picks text archive | `signal-desk/intelligence/splash_picks/processed/<date_code>.txt` |
| Picks comparison | `signal-desk/intelligence/splash_picks/<date_code>.md` |

Read the receipt's `actual_new_rows`, duplicate list, SHA-256, and `airtable_writes: 0`, then verify that the receipt and outputs exist in the successful processing commit. Ticket probabilities in a comparison are processing-time reconstructions, not proof of a saved pregame forecast; reference payout calculations are not a statement of actual contest winnings.

## Important boundaries

- **Missing Ledger games**: This route requires exactly one existing Ledger match per game and never creates Ledger rows. The existing ESPN sync enriches existing rows; it does not provision the next week's schedule. Report missing schedule coverage as a separate dependency, with the time and scope of the read. Do not send the owner through repeated extractions to fix it.
- **Read-only schedule boundary**: Keeping Airtable read-only means an assistant cannot solve absent Ledger rows by creating them. Either an owner-managed schedule process must supply the existing Ledger rows, or a separately approved architectural change must add repository-only game identities and adapt their consumers. The second option is not implemented by this inbox and must never masquerade as Airtable matches.
- **Invalid dumps**: Derive the diagnosis from the newly attached file. Do not copy counts or dates from a historical report. Ask for source verification and a newly extracted complete file when header and body disagree; do not guess which field is wrong.
- **Historical line discrepancies**: A guard in closing capture preserves a populated total going forward. It does not repair historical differences between saved early snapshots and current Ledger values.
- **Existing scheduled prompts**: This guide does not establish their current state. The import workflow does not require a Computer automation run. Do not tell the owner to run one for each dump, or infer that a saved prompt changed merely because repository code changed.
- **Surface availability**: If regular chat lacks the repository-file action, this exact chat-only path is not verified for that surface. Do not claim otherwise or ask the owner to paste credentials; decide a separately authorized ingestion route instead.
- **Safety**: Do not put access tokens in JSON, workflow inputs, source code, or prompts. Public raw-file storage needs explicit owner approval every time.

## Deployment acceptance

For a new implementation, an approved push and separately approved PR come before the owner's review and merge. For this installed implementation, check the actual current main-branch files and workflow rather than repeating an obsolete "not merged" statement. Then test the regular-chat file action without a write, verify existing schedule coverage, submit one fresh valid owner dump with its own exact-file approval, and verify the resulting production commit and reports.

Keep Airtable read-only throughout. Do not declare the whole system ready until schedule coverage, data freshness, and the readiness gate also pass.
