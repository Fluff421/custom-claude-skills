#!/usr/bin/env bash
# Commit data-only files to main as the bot, with a rebase-and-retry so overlapping scheduled runs do not clash.
# Usage: commit_data.sh "message" path [path ...]
# Optional COMMIT_DATA_REGEN: shell commands that rebuild the outputs; when set, a rebase
# conflict resets to origin/main, reruns them and retries instead of failing.
set -euo pipefail
msg="$1"; shift
git config user.name "signal-desk-bot"
git config user.email "signal-desk-bot@users.noreply.github.com"
git add -N "$@" 2>/dev/null || true
if git diff --quiet -- "$@"; then echo "No change to commit."; exit 0; fi
git add "$@"
trailer="Co-authored-by: Perplexity <noreply@perplexity.ai>"
commit_outputs() {
  if [[ "$msg" == *"$trailer"* ]]; then
    git commit -q -m "$msg"
  else
    git commit -q -m "$msg" -m "$trailer"
  fi
}
commit_outputs
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
    if [ -n "${COMMIT_DATA_REGEN:-}" ] && [ "$i" -lt 4 ]; then
      # Another producer pushed the same generated files. Rebuild from the newest main
      # instead of hand-merging generated data, then commit and try again.
      echo "Rebase conflicted with a newer main; regenerating outputs from origin/main (attempt $i)."
      git fetch -q origin main
      git reset -q --hard origin/main
      bash -euo pipefail -c "$COMMIT_DATA_REGEN"
      git add -N "$@" 2>/dev/null || true
      if git diff --quiet -- "$@"; then echo "No change to commit after regeneration."; exit 0; fi
      git add "$@"
      commit_outputs
      continue
    fi
    echo "::error::Data publication failed while rebasing; outputs were not published."
    exit 1
  fi
  sleep $((i * 5))
done
echo "::error::Could not push data commit after retries"; exit 1
