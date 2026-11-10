# Splash Sports imports from regular chat

Status: proposed implementation, not enabled until the change is reviewed and merged into `main`. This is a repository-only import path for the owner's native File 1 lines and File 2 picks JSON; it never writes to Airtable.

## The simple routine

- **Prepare**: Use your existing owner-run extraction to obtain the complete Splash JSON. Do not change counts, dates, lines, or results to make a file pass.
- **Open regular Search**: Before the first message, select GitHub with the paperclip. Typing `@GitHub` alone does not select it, according to [Perplexity's troubleshooting instructions](https://perplexity.ai/help-center/en/articles/2026091803-troubleshooting-the-github-connector).
- **Verify the action once**: Ask the connected GitHub integration whether this regular-chat surface exposes a repository-file creation/update action for `Fluff421/custom-claude-skills`. Do not perform a write during this check. [Perplexity documents GitHub actions generally](https://www.perplexity.ai/help-center/en/articles/12275669-github-connector-for-enterprise), but that article does not establish that every regular-chat surface exposes this particular action.
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

Read signal-desk/SPLASH_IMPORT.md and identify the schema and date_code.
For File 1 use signal-desk.splash-lines.v1.
For File 2 use signal-desk.splash-picks.v1.
Prepare exactly:
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

No Airtable writes, variable changes, result patches, or hand-edited CSVs.
All picks are paper picks; verify against your Splash line before locking.
```

For a commit created by the assistant, retain the user's authorship and end the message with `Co-authored-by: Perplexity <noreply@perplexity.ai>` exactly once. Each import is a separate approval; approval of the implementation is not blanket approval to publish later dumps.

## What the new workflow does

- **Accepted inputs**: One newly supplied JSON file per owner-authored push to `main`. Native lines and pending/completed picks use the same inbox.
- **Validation**: Supported schema and exact source; safe date code; timezone-aware extraction timestamp; no unresolved warnings; finite numeric lines; parseable Central kickoff; seasonally correct Central timezone label if supplied; correct spread signs; exact per-league counts and unique games.
- **Freshness**: Lines and completed-pick extractions must be at most 24 hours old; pending-pick extractions at most 12 hours old. Anything older than four hours is flagged even if still within its import limit.
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

- **Missing Ledger games**: This route rejects zero-match games and never creates Ledger rows. The November 9 owner dump's 81 listed games had no matching Ledger rows in the November 10 read-only audit; changing transport does not provision the new schedule.
- **Current invalid dump**: Its header declares 16 NFL and 63 NCAAF entries, while its body contains 14 NFL and 67 NCAAF entries. Request a corrected fresh owner extraction, not an edited header or a stale-data override.
- **Historical line discrepancies**: A guard in closing capture preserves a populated total going forward. It does not repair historical differences between saved early snapshots and current Ledger values.
- **Existing scheduled prompts**: The weekly Computer task still describes database writes and manual dispatch. That conflicting task must be separately reviewed before anyone uses it as the new import route.
- **Surface availability**: If regular chat lacks the repository-file action, this exact chat-only path is not verified for that surface. Do not claim otherwise or ask the owner to paste credentials; decide a separately authorized ingestion route instead.
- **Safety**: Do not put access tokens in JSON, workflow inputs, source code, or prompts. Public raw-file storage needs explicit owner approval every time.

## Deployment acceptance

After an approved implementation push and separate PR approval, the owner reviews and merges. Then test the regular-chat file action without a write, submit one fresh valid owner dump with its own exact-file approval, and verify the resulting production commit and reports.

Keep Airtable read-only throughout. Do not declare the whole system ready until schedule coverage, data freshness, and the readiness gate also pass.
