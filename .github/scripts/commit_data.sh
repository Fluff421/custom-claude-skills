#!/usr/bin/env bash
# Commit data-only files to main as the bot, with a rebase-and-retry so overlapping scheduled runs do not clash.
# Usage: commit_data.sh "message" path [path ...]
set -euo pipefail
msg="$1"; shift
git config user.name "signal-desk-bot"
git config user.email "signal-desk-bot@users.noreply.github.com"
git add -N "$@" 2>/dev/null || true
if git diff --quiet -- "$@"; then echo "No change to commit."; exit 0; fi
git add "$@"
git commit -q -m "$msg"
for i in 1 2 3 4; do
  if git pull --rebase -q origin main; then
    git push -q origin HEAD:main && { echo "Pushed."; exit 0; }
  else
    git rebase --abort 2>/dev/null || true   # same file changed by an overlapping run; next run regenerates it
    echo "::warning::Rebase conflict on data files; skipping this commit (the next scheduled run recomputes it)"; exit 0
  fi
  sleep $((i * 5))
done
echo "::error::Could not push data commit after retries"; exit 1
