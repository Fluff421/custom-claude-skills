# Splash Sports imports from regular chat

This is the authoritative intake contract for Signal Desk in `Fluff421/custom-claude-skills/signal-desk/`. Airtable base `appSfcG682952AQAv` is read-only for this import path. Native JSON intake, model readiness, and background Airtable writers are separate systems; an accepted import does not establish that recommendations are ready or that unrelated jobs are read-only.

## Deployment and scope

Read current main, not an earlier guide's status. Native intake requires `splash_import.py` and `.github/workflows/splash-json-inbox.yml`; repository-only references require `repo_schedule.py`; owner reviews and durable status require `splash_submission.py` and a workflow that watches `splash_import/reviews/*.json`. A branch, passing unit test, or saved inbox file is not production acceptance.

The import workflow uses Python and GitHub Actions, not Computer or a model API. Regular Search and connector limits still apply. This contract does not promise free service usage, a supported write action in every chat, or byte-exact transport where the chat cannot provide it.

## Owner routine

1. Run the owner-only line extractor in `SPLASH_EXTRACTION_LINES.md`, or the pick extractor in `SPLASH_EXTRACTION_PICKS.md`. Save the actual JSON, not the extraction instructions.
2. Open regular Search with GitHub selected. Use the literal preparation prompt in `CHAT_PROMPTS.md`, then paste the complete original JSON alone in the next message when it fits. Use an attachment only if its reader supplies complete exact content.
3. Review the exact repository, main branch, computed filename, full proposed content, public-data warning, and commit message. Approve that specific write. Imports are never blanket-authorized.
4. The chat submits the unchanged approved JSON through a callable file-write action, preferably single-file `push_files` with literal UTF-8 content. It does not launch Computer, dispatch a workflow, or ask you to edit GitHub.
5. Read the committed submission status and receipt. A rejection stays pending with its original file; the chat reports the first rejection reason and any other verified blockers. It does not re-upload the same source as a retry.
6. If factual confirmation is needed, the chat prepares a separate checksum-bound review. Approve its exact content before its one write. The review triggers processing of the original pending source; raw JSON remains unchanged.

File 2 does not always need a new File 1 first. Existing Ledger games or accepted repository references are sufficient. File 1 is needed first only for games absent from both.

## Transport gate

The November 10, 2026 test succeeded for SPL-C-20261110-1139: a preparation-only message supplied the complete approved review, a second message supplied the complete 37,075-byte original, and Search's confirmation gate led to one approved two-file push. Read-back matched the original and review checksums, and production accepted one new row while skipping 16 duplicate tickets ([input commit](https://github.com/Fluff421/custom-claude-skills/commit/21d5f70cf588c11987822a7dd70f6208998d6164), [accepted status](https://raw.githubusercontent.com/Fluff421/custom-claude-skills/923f7284e6548d0d17773e2c0cc32e8ce094f930/signal-desk/intelligence/splash_import/status/SPL-C-20261110-1139.json)).

This verifies that specific literal-text route, not every chat or source size. The attachment reader truncated File 1, and a one-message File 1 literal exceeded the observed 40,000-character input limit; those attempts made no Search write. Keep each complete message below that observed limit, including instructions. A separately staged review is not a separate write; all exact approved files must be available before the single push.

Future extractors produce compact single-line JSON from the outset, without omitting observations. Existing originals retain their exact text and terminal-newline state. If a complete source still cannot fit or exact content is unavailable, stop; larger multipart-source assembly is untested. Never replace missing text with a preview, ellipsis, reconstructed data or an invented checksum.

Show the complete payload and obtain exact owner approval before writing. If Search asks for a confirmation, it must cover that same approved payload only. A content or execution failure ends that attempt; a fallback or retry requires a new exact approval. Acceptance remains separate from recommendation readiness ([readiness at acceptance](https://raw.githubusercontent.com/Fluff421/custom-claude-skills/923f7284e6548d0d17773e2c0cc32e8ce094f930/signal-desk/intelligence/splash_import/readiness_latest.json)).

## What Search must and need not do

- **Access:** Run GitHub get_me when exposed; read current ASK_SIGNAL_DESK.md, this contract, and picks_latest.md. Discover the callable action schema. Distinguish tool exposure, successful reads, and an executed approved write.
- **Source review:** Identify the actual JSON attachment, schema, date_code, timestamp, warnings, coverage, and obvious contradictions. Do not call an extraction-instructions Markdown file a dump. Complete source text must be available before proposing publication.
- **Server authority:** The repository performs exact counts, hash computation, uniqueness/orientation checks, Ledger reads, duplicate detection, and generated-output checks. A Search environment's inability to execute Python or read Airtable is not itself a bad-dump diagnosis or a demand for another extraction.
- **Byte fidelity:** Preserve original text and line endings when available. If exact original attachment bytes or their checksum cannot be verified, disclose that before approval. Never claim an original-attachment hash from the server's committed-file checksum alone. Stop if the transport cannot preserve the owner-approved content.
- **Readiness:** Intake may proceed for validation and recording even when old recommendations are stale. Recommendation readiness is a separate gate; import success cannot satisfy missing ratings, fresh narratives, producer evidence, or requested-window coverage.
- **Publication:** Show complete exact proposed contents, not merely a filename or summary. Warn that this PUBLIC repository reveals supplied contest links, entry names, stakes, payouts, tickets, and other raw details. Each approval covers one specifically described write only.

For an assistant-authored commit, retain the user as author and end with the trailer `Co-authored-by: Perplexity <noreply@perplexity.ai>` exactly once. PRs and comments use the owner's required attribution footer. Never merge, change variables, write Airtable, or edit generated CSVs.

## Validation and observations

- **Freshness:** More than four hours old is a warning. Hard maximums are 24 hours for lines/completed extractions and 12 hours for pending extractions. Future timestamps beyond five minutes are rejected. Never relabel an old observation as fresh.
- **Lines:** Supported schema/source; safe date_code; exact league counts; finite signed opposite spreads and total; actual Central kickoff and appropriate CST/CDT label; certain orientation for a new repository reference. Each game must be unique.
- **Counts:** Build the games array first, then count its league tags. Preserve page widgets separately. A mismatch alone establishes neither which league tag is wrong nor that coverage is incomplete. A review can derive counts from the array only after the owner confirms the captured array is the intended complete board.
- **Warnings:** Unresolved warnings still reject. Informational notes can live in `notes`; they must not conceal uncertainty about required observations. An exact warning and its explicit owner resolution can be preserved in a checksum-bound review without deleting anything from the original.
- **Prices:** A displayed +100 is not automatically an extraction error. Preserve displayed odds exactly; do not replace a board-wide even-money price with -110. Missing spread/total leg prices may remain null. Moneylines require their actual valid American price.
- **Matching:** League, date within one day, and both teams must identify one existing game, with correct orientation. Exact labels take priority. A partial word overlap in an unrelated matchup is not a complete game match. Viable ambiguous or reversed matches remain errors.
- **Names:** Preserve observed nicknames. After the existing game is uniquely matched, a selection may expand only to the uniquely identifying team within that matched pair. Generated picks text uses the matched full names; no invented alias dictionary is used.
- **Completed dates:** A completed leg can match by explicitly observed `game_date_central` when actual kickoff is unavailable. A checksum-bound review may supply an explicitly owner-confirmed matching date. Placement, settlement, extraction time, ticket IDs, and contest-year labels are not substitute game dates. Pending picks and File 1 still require actual kickoff. Date-only matching never creates new games or invents a kickoff.
- **Teasers:** Preserve the explicitly observed final teased number; never fill a null teased_line. A missing base_line stays unknown in native intake, without reconstructed base-line movement or a probability requiring that unknown base. Legacy text handling remains separate.
- **Duplicates:** Compare complete ticket type/game/market/side/number identity, including moneyline price. Skip whole previously recorded tickets. Changed source-ticket identity requires review. Count games, tickets, and legs separately.
- **History:** Raw source, original metadata, early quotes and accepted reviews are immutable. New movement appends observations; it never repairs an earlier number. Reported owner settlement is metadata, not independently verified scoring or a saved pregame forecast.

## Owner-review contract

Reviews live in `signal-desk/intelligence/splash_import/reviews/` with exactly the source JSON's filename. They are authorized only through approval of their exact contents. Supported schema is `signal-desk.splash-review.v1`; required fields are `date_code` and `input_sha256` bound to the original source bytes.

Optional fields:
- **count_policy:** Exactly `owner_confirms_complete_games_array`, for File 1 only. Derive effective counts; retain original counts in the receipt.
- **warning_resolutions:** Array of objects containing exact `warning` text and nonblank `resolution`. Unlisted warnings remain blocking.
- **completed_game_dates:** For completed picks only. Each object contains exactly `ticket_id`, zero-based `leg_index`, and `game_date_central` in YYYY-MM-DD format. It cannot inject kickoff, replace an observed date/time, or create a game.

All other review changes reject. Reviews cannot change teams, league tags, lines, odds, teased values, ticket dates/IDs, extraction timestamps, results, or money. The importer applies permitted metadata resolutions only to a working copy, archives the original bytes, and saves the complete review and its SHA-256 in the receipt.

One owner push may contain one original inbox file, one review for an already-pending source, or the original and its same-code review together. Different source date_codes in one push reject. A review-only recovery never recreates or overwrites an accepted source.

## Repository-only coverage and model boundaries

A validated File 1 may establish stable owner-source `repo-game:` references without creating Airtable rows. These are not independently verified schedules. File 2 only matches existing Ledger games/references. Later real Ledger bindings preserve identity and first quote.

Missing verified finite Home/Away FPI means unpriced, including spread, total, moneyline, teaser, and combination recommendations. New references do not magically enter the primary market engine or calibration. Accepted lines do not repair this missing producer. Available Ledger scores may grade the official recorded Splash numbers in a separate derived reconciliation view.

## Reading acceptance and failures

Paths below are relative to signal-desk; form each filename from the actual JSON date_code rather than copying a placeholder.

| Item | Directory or file |
|---|---|
| Pending source | intelligence/splash_import/inbox/ |
| Owner review | intelligence/splash_import/reviews/ |
| Submission status | intelligence/splash_import/status/ |
| Accepted receipt | intelligence/splash_import/receipts/ |
| Processed original | intelligence/splash_import/processed/ |
| Line raw archive and report | intelligence/splash_lines/raw/ and intelligence/splash_lines/ |
| Pick raw archive and report | intelligence/splash_picks/raw/ and intelligence/splash_picks/ |
| Full-name generated picks text | intelligence/splash_picks/processed/ |
| Reference catalogue | intelligence/splash_import/schedule.json |
| Derived grading | intelligence/splash_import/reconciliation/latest.json |

Acceptance requires committed status=accepted, accepted receipt, checksum agreement with the committed input and raw archive, expected versus actual row counts, duplicate skips, exact reference origins/game dates/orientation, reports, and airtable_writes=0. Read related outputs at the same processing commit. A local replay, queued job, green unrelated run, or input save is not completion.

After accepted processing, `intelligence/splash_import/readiness_latest.json` contains an actual execution of the existing readiness validator, not an inferred pass. Read its checked_at, source_revision, errors and input_git_blobs. Those Git blob identities can be checked against the file identities returned by the GitHub connector without pretending Search ran Python. A fresh readiness decision about stale observations still fails; missing files, changed inputs, missing ratings or window coverage cannot be waived. The submission status's artifacts_ready flag reports that validator only; requested_window_coverage_checked remains false because intake does not establish recommendation coverage or verified model inputs.

Rejected/failed processing restores pre-run generated files and publishes a failure status without an accepted receipt. The first error is not an exhaustive independent-blocker audit. A commit/push failure can leave no new status on main; report acceptance as unverified rather than manufacturing success. Keep pending originals for separately approved review; do not silently resubmit.

## Legacy route

The older owner-approved full-name text inbox remains legacy. Convert with explicit Parlay: or Teaser: labels and teased suffixes; never infer a null teased number. Native JSON is the preferred path and does not require an owner-written intermediate text file.
