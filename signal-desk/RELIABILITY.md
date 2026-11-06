# Signal Desk Reliability Review and Implementation

The reliability recommendations are sound with corrections to paths, evidence requirements and producer coordination. The owner authorized production deployment on November 6, 2026, and [PR #51](https://github.com/Fluff421/custom-claude-skills/pull/51) was merged. Production validation remains separate from deployment: no healthy result may be inferred from a merge or green CI, and secrets, existing live-mode settings and paper-pick gates remain unchanged.

## Capabilities and scope

- **Repository implementation:** Local file edits, Python execution, repository access and workflow-log access are available. Grok does not need to implement these repository changes.
- **Live operation:** A branch or pull request does not activate scheduled production changes. Merge, an initial successful producer run and consumer integration are still needed.
- **External scheduling:** No verified control of Grok's external schedule was established. Moving its monitor is not a substitute for repairing the actual producers.
- **Splash quotes:** File 1 contains owner-supplied Splash quotes as of its capture time. These are not a direct live Splash connection or a promise that the quote is still available.

## Pull-request validation versus production health

PR #51's initial failures exposed two different concerns: deterministic code validation was calling live services and checking current production freshness, while DraftEdge had replaced its table rows with team/player cards. PR checks must verify the code without requiring today's production data to be healthy.

The six producer workflows now route pull requests to a shared offline-contract workflow, with read-only repository permissions, no inherited service secrets and no external feed/database calls. Their production jobs do not execute on pull requests. Existing production concurrency groups are preserved; PR-specific groups prevent review checks from queuing behind or delaying production jobs.

Scheduled and manual producer/readiness runs retain their actual live-data checks and nonzero failures. A green pull-request check is not a claim of clean feed coverage, fresh grading or three healthy days.

The DraftEdge parser now accepts the observed card layout and the legacy table layout. Regression fixtures cover nested team names, attribute order, incomplete cards, empty responses, missing source timestamps and genuine no-game windows. A read-only replay of the [November 6 provider page](https://draftedge.com/cfb/college-football-injury-report/) parsed 401 entries across 134 teams, but no source updated-at timestamp was published. That missing timestamp remains an explicit production-health failure rather than being replaced with the fetch time.

## Readiness policy

`validate_artifacts.py` is a standard-library-only, read-only check unless `--output` is supplied for a diagnostic JSON file. Missing, empty, malformed, future-dated or stale required metadata fails closed with exit code 1. Checkout modification times are never treated as source freshness.

| Evidence | Default requirement |
| --- | --- |
| Narrative | Today's Central-date JSON and Markdown; JSON generation age under 4 hours |
| Canonical JSON | `intelligence/latest.json` equals `intelligence/data/YYYY-MM-DD.json` |
| Narrative pairing | New reports include a Markdown content digest in the JSON |
| Close & Grade | Latest non-PR run started under 2 hours ago, successful, operationally healthy and LIVE |
| Splash board | `intelligence/splash_lines/latest.md`, source capture age under 12 hours |
| Canonical price check | `intelligence/splash_pricecheck/latest.md` and `.json`; generation age under 4 hours |
| Underlying price-check quotes | Age reconstructed from generation time and snapshot age; under 12 hours |
| Operational evidence | `data/ops_status.json` generated under 4 hours ago |
| Required producer evidence | ESPN/picks under 4 hours, Context under 26 hours; injury under 4 hours Wed–Sat, 26 hours otherwise. Missing, unhealthy, unsuccessful or non-LIVE evidence fails |
| Snapshot export | Explicit generation timestamp under 26 hours; a checkout or file modification time is not evidence |
| Known producer degradation | Fail if operational evidence records an unhealthy upstream run or market-feed failure |

The 4-hour narrative and market warning policy is intentionally retained rather than silently relaxed to the proposed 12 hours. Board freshness uses the stricter end of the proposed 12–24-hour range. The limits can be explicitly overridden through named CLI options; changing them is a policy decision, not a way to conceal stale evidence.

Board/underlying-quote ages between 4 and 12 hours remain visible warnings even when artifact readiness passes. The market builder's Splash moneyline preference is stricter: only quotes under 4 hours old can replace estimates.

Operational missed-run thresholds use 2 hours for grading, 4 hours for ESPN and picks, and 26 hours for context/Snapshot. Injury cadence uses 4 hours on its frequent-run days and 26 hours on its daily-run days; the separate BIM board's policy is unchanged.

```bash
# Run from the repository root. This makes no network calls or external writes.
python signal-desk/validate_artifacts.py

# Preserve the check result without altering source evidence.
python signal-desk/validate_artifacts.py \
  --output signal-desk/data/artifact_validation.json

# Reproducible diagnostic against a chosen clock.
python signal-desk/validate_artifacts.py --now 2026-11-06T14:30:00Z
```

Readiness is an artifact gate, not proof of three healthy days or permission to promote paper picks. The tier/league sample counts, positive CLV and calibration checks remain separate.

## Producer reliability and observations

- **Snapshot:** Runs the readiness check after generation. A failed gate keeps the job red while preserving diagnostic evidence and any available valid outputs. Partial market-feed failures now exit nonzero after writing their diagnostic sidecar.
- **Injury pull:** Either required source being unavailable or invalid is a failure when games are expected. Valid partial observations may still be retained, but they cannot produce a healthy success result. A genuine zero-game window is not treated as a dropout.
- **Close & Grade:** Missing league coverage, missing expected events, incomplete competitors and incomplete final scores are recorded as errors. Valid games may still be processed before a nonzero exit reports partial coverage.
- **Heartbeats:** `data/source_heartbeats.json` records per-game `checked_at` separately from `changed_at`. It covers successfully matched ESPN observations only, not every row merely because a job started.
- **Health reporting:** Matching event-ID heartbeats inform ESPN freshness without adding Airtable columns or making timestamp-only database writes. Injury workflow health is also included, with known partial-source warnings classified as degraded.

Successful no-change runs remain valid. Source record dates, checked-at times, report generation times and kickoff times have different meanings and are not interchangeable.

## Producer coordination

| Workflow | Deployed schedule, America/Chicago |
| --- | --- |
| Context & Calibrate | 06:13, with UTC offset selection |
| Close & Grade | Existing hourly cadence at minute 37, unchanged |
| Snapshot | 07:47, with UTC offset selection |
| Briefing Readiness | 08:23, with UTC offset selection |
| Existing briefing consumer | 08:30, unchanged |

The offset gates select the correct UTC candidate without requiring the runner to start within the intended local hour. These are scheduling margins, not delivery guarantees; actual timestamps and conclusions still control readiness. The new pre-briefing check refreshes operational evidence read-only and preserves its result as an execution artifact.

Grok's observed role is monitoring, not production. Its timing can be coordinated separately if the owner has access, but the repository's readiness must not depend on Grok repairing missing artifacts.

## Repricing, prices and CLV

- **Probability refresh:** The existing probability-drift threshold of 0.005 remains intact. A stable model-input fingerprint adds feature/sigma/configuration refresh reasons even below that threshold.
- **Fingerprint storage:** The fingerprint is stored in the existing data-completeness text field and preserved in repricing notes. No new database schema is needed; timestamp-only ESPN checks do not change the fingerprint.
- **Safeguards:** The existing pending-pick, kickoff and `REPRICE_LIVE` checks still control actual saves. Graded/started picks are not opened for repricing by this change.
- **Quote preference:** The market builder can prefer File 1 moneylines under 4 hours old with known future kickoff, using their paired Splash spread for that moneyline projection. Quote source, snapshot ID and capture time remain explicit; the original Ledger line is not modified.
- **Missing prices:** Estimated moneyline prices remain clearly marked research observations with No Play and zero units. They cannot become positive-unit recommendations merely because an estimated edge looks attractive.
- **Close provenance:** CLV calculation requires explicit pregame close-capture evidence. Missing or malformed timestamps and post-capture observations are rejected, and chronological order is used rather than file append order. A later live capture cannot borrow an earlier pregame label.
- **Existing examples:** Buffalo +6.5 versus +7 is already -0.5 CLV; Akron +12.5 versus +13.5 is already -1.0 CLV in the checked CSV. Both use the Ledger's November 3 23:39Z pregame ESPN/DraftKings capture notes, not a claimed Splash closing quote. No CSV rewrite was necessary for either row.

Imported-to-locked differences remain line movement, not bad data. This implementation does not change the official locked line, live factor mode, learning gates or unit caps. Nothing is tuned below its applicable gate; base sigma retains its existing historical-plus-ledger residual learning rather than acquiring a universal 30-live-game requirement. Factor adjustments drive picks only if the owner enables live factor mode.

## Activation and consumer integration

Review and merge the branch only after inspecting the code, deterministic tests and workflow validation. Keep current live-mode variables unchanged. Inspect the first actual producer outputs, failure diagnostics and heartbeat before relying on the new checks.

The existing 08:30 Central briefing instructions now require a read-only validation against current main. Its schedule, destination and notification settings are preserved. Its ten sections remain intact, but an unavailable or failed gate blocks current recommendations:

> Before generating the daily briefing, obtain a fresh current-main checkout. Run `python signal-desk/validate_artifacts.py --root signal-desk` and inspect its exit status, JSON errors and warnings. Corroborate it with the latest production readiness execution and artifact. If the command is unavailable, fails, or reports `ready: false`, open with NOT READY and identify failed checks; preserve the ten sections with historical/unavailable labels and withhold current recommendations. If it passes, carry freshness warnings into the paper-pick briefing and separately evaluate all promotion gates. Do not write to Airtable, modify workflow variables or dispatch workflows from the briefing.

The 08:23 readiness workflow supplies an additional observable check. A delayed or missing readiness execution is not evidence of health. Health evidence includes chained main-branch pick refreshes after Context & Calibrate and successful injury refreshes, while excluding non-main runs. DraftEdge remains invalid when it does not publish a source update timestamp; a validated full-coverage replacement may satisfy the secondary-source requirement without pretending DraftEdge itself is healthy.

## Timestamped injury replacement

[Kickoff Status](https://kickoffstatus.com/) publishes explicit, timezone-aware data-refresh times and separates conference availability tables from unofficial notes. A [current game report](https://kickoffstatus.com/games/2026-11-06-tcu-at-arizona/) also provides structured event identity. These are source-provided snapshot times, not a locally invented fetch or page-build date.

When DraftEdge is invalid, the injury producer can use Covers plus this replacement. Every pending, non-past NCAAF Ledger game must match a report by date and both teams; every report needs both structured team tables, known player statuses and a fresh publisher timestamp. Missing or conflicting games, partial teams, unknown statuses, stale timestamps and unverified empty tables fail closed. Explicit Available rows can establish a genuine zero-injury report without manufacturing entries.

Only conference availability tables enter model notes; unofficial rumors are excluded. For covered games, the current availability report supersedes old unofficial statuses, including clearing old Out labels for now-Available players. Covers remains a required cross-check source. Diagnostics retain DraftEdge's failure separately and record the actual replacement provider, report URLs, source snapshot times and expected/covered game counts.

Graded and past games are untouched, manual notes remain protected, and the only Airtable write field remains Injury Notes. Direct public reads use two workers and bounded request/job timeouts, without new credentials or paid-feed calls. A successful injury refresh on main triggers the existing guarded Pick Engine so changed injury features are repriced without waiting for its next scheduled slot.

## Verification

Run all deterministic tests from `signal-desk`:

```bash
python -m unittest discover -s tests -v
```

The tests cover missing and stale artifacts, degraded success states, invalid metadata, JSON/Markdown pairing, source-age preservation, heartbeat change semantics, feature/sigma refresh, real-versus-estimated prices and conservative close provenance. Workflow syntax and Python compilation should also be checked before merge. Passing offline checks does not establish live feed health or restore the three-day promotion requirement.

Local verification on November 6, 2026: all 203 deterministic tests passed, Python compilation passed, and workflow syntax and expression validation passed. The pre-change baseline was 168 passing tests. Existing resource warnings from older tests are unrelated to the new checks; the deliberate unavailable-source test also exercises the nonzero error path. Regressions cover missing required producers, stale healthy runs, successful dry runs, missing Snapshot timestamps, chained main-branch pick refreshes, complete/incomplete replacement coverage, stale/absent source stamps, UTC kickoff dates, available/not-listed players, distinct full names, manual-note protection, verified school aliases, unpublished official reports, missing positions and graded-game preservation.
