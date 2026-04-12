#!/bin/bash
# sync-github.sh — Authenticated GitHub force-pull then force-push
# Requires GITHUB_TOKEN to be set in the environment.
# Usage: bash sync-github.sh

set -e

REMOTE="https://github.com/pilunohq-afk/VIT.git"
BRANCH="${GIT_BRANCH:-main}"
USER_NAME="${GIT_USER_NAME:-pilunohq-afk}"
USER_EMAIL="${GIT_USER_EMAIL:-pilunohq@gmail.com}"

if [ -z "$GITHUB_TOKEN" ]; then
  echo "ERROR: GITHUB_TOKEN is not set. Add it to Replit Secrets and restart." >&2
  exit 1
fi

restore_remote() {
  git remote set-url origin "$REMOTE" 2>/dev/null || true
}
trap restore_remote EXIT

echo "=== VIT GitHub Sync ==="
echo "Branch : $BRANCH"

git config user.name  "$USER_NAME"
git config user.email "$USER_EMAIL"

git remote set-url origin "https://${GITHUB_TOKEN}@github.com/pilunohq-afk/VIT.git"

# Step 1: Force push local state to remote so remote matches local
echo "--- Step 1: Force push local → origin/$BRANCH ---"
git push --force origin "HEAD:$BRANCH"
echo "Force push complete. HEAD: $(git rev-parse --short HEAD)"

# Step 2: Fetch and reset to origin to confirm sync (no-op since we just pushed)
echo "--- Step 2: Force pull (fetch + reset --hard) ---"
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"
echo "Force pull complete. HEAD: $(git rev-parse --short HEAD)"

echo "=== Sync finished successfully ==="
