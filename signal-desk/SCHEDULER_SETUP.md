# Free External Schedule Setup (cron-job.org)

This replaces late GitHub schedules for the jobs that matter most. GitHub's own schedules stay on as a backup; duplicate runs wait their turn safely because each workflow runs one at a time.

## Step 1. Create a limited GitHub token (5 minutes)

1. On GitHub, open Settings, then Developer settings, then Personal access tokens, then Fine-grained tokens, then Generate new token.
2. Name: `signal-desk-cron`. Expiration: 1 year (set a calendar reminder to renew).
3. Repository access: Only select repositories, choose `Fluff421/custom-claude-skills`.
4. Repository permissions: Actions = Read and write. Leave everything else as No access.
5. Generate and copy the token. Paste it only into cron-job.org; never into a chat.

## Step 2. Create the cron-job.org account

Sign up free at cron-job.org. In Settings, set the time zone to America/Chicago.

## Step 3. Create three jobs

For each job: Create cronjob, then fill in:

- Request method: POST
- Headers (Advanced tab):
  - `Accept: application/vnd.github+json`
  - `Authorization: Bearer <your token>`
  - `X-GitHub-Api-Version: 2022-11-28`
- Treat HTTP 204 as success (the default success range covers it).
- Notifications: email on failure.

| Job name | URL | Body | Schedule (Central) |
|---|---|---|---|
| SD Context & Calibrate | `https://api.github.com/repos/Fluff421/custom-claude-skills/actions/workflows/context-calibrate.yml/dispatches` | `{"ref":"main","inputs":{"live":"true"}}` | Daily 6:13 AM |
| SD Close & Grade | `https://api.github.com/repos/Fluff421/custom-claude-skills/actions/workflows/close-grade.yml/dispatches` | `{"ref":"main","inputs":{"live":"true"}}` | Every hour at :37 |
| SD Briefing Readiness | `https://api.github.com/repos/Fluff421/custom-claude-skills/actions/workflows/briefing-readiness.yml/dispatches` | `{"ref":"main"}` | Daily 8:23 AM |

Snapshot and Pick Engine start automatically when Context & Calibrate finishes, so they do not need their own jobs.

## Step 4. Test

Use Test run on each job. A 204 response means GitHub accepted it. Then open the repository's Actions tab and confirm a new run of that workflow appears within a minute, with the event shown as workflow_dispatch.

## Step 5. Confirm over two mornings

Ask Perplexity prompt P2 (ops health) after 8:30 AM. Context should start by about 6:15 AM, Snapshot should finish before 8:30 AM, and the daily briefing should pass the readiness gate if everything else is fresh.

To stop: pause the jobs in cron-job.org and revoke the token on GitHub.
