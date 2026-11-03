#!/usr/bin/env bash
# Usage: offer-fix.sh <pr number> <bot login>
# Adds, or resets to unticked, the comment whose checkbox starts the Claude Fix workflow.
set -euo pipefail

pr="$1"
bot="${2%\[bot\]}"
repo="$GITHUB_REPOSITORY"
marker="<!-- claude-review-fix -->"
body="$marker
- [ ] Apply the fixes from the latest review, run the tests, and put the result on a devbox

A maintainer can tick the box to start it."

comment=$(gh api --paginate "repos/$repo/issues/$pr/comments" --jq '.[]' \
	| jq -r --arg bot "$bot" --arg marker "$marker" \
		'select((.user.login == $bot or .user.login == ($bot + "[bot]")) and (.body | startswith($marker))) | .id' | tail -1)

if [ -n "$comment" ]; then
	gh api -X PATCH "repos/$repo/issues/comments/$comment" -f body="$body" --silent
else
	gh api -X POST "repos/$repo/issues/$pr/comments" -f body="$body" --silent
fi
