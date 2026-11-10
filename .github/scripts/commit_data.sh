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
trailer="Co-authored-by: Perplexity <noreply@perplexity.ai>"
if [[ "$msg" == *"$trailer"* ]]; then
  git commit -q -m "$msg"
else
  git commit -q -m "$msg" -m "$trailer"
fi
for i in 1 2 3 4; do
  # Producers may update another tracked sidecar outside the selected publish
  # scope. Preserve that local work while rebasing only the committed outputs.
  if git pull --rebase --autostash -q origin main; then
    if [ -n "$(git ls-files -u)" ]; then
      echo "::error::Autostash restoration conflicted; no output push performed."
      exit 1
    fi
    git push -q origin HEAD:main && { echo "Pushed."; exit 0; }
  else
    git rebase --abort 2>/dev/null || true
    echo "::error::Data publication failed while rebasing; outputs were not published."
    exit 1
  fi
  sleep $((i * 5))
done
echo "::error::Could not push data commit after retries"; exit 1
