#!/usr/bin/env bash
# shellcheck disable=SC2016
# Usage: review-context.sh <pr number> <bot login> <output dir>
# Needs GH_TOKEN and GITHUB_REPOSITORY. Reads REVIEW_REQUEST for the text of the comment that asked for the review.
set -euo pipefail

pr="$1"
bot="${2%\[bot\]}"
out="$3"
repo="$GITHUB_REPOSITORY"
mkdir -p "$out/issues"

gh pr view "$pr" --repo "$repo" \
	--json number,title,body,author,baseRefName,headRefOid,labels,isDraft,files \
	> "$out/pr.json"

printf '%s\n' "${REVIEW_REQUEST:-}" > "$out/request.txt"

gh pr checks "$pr" --repo "$repo" > "$out/checks.txt" 2>&1 || true

{
	gh api graphql -F owner="${repo%%/*}" -F name="${repo##*/}" -F number="$pr" \
		-f query='query($owner: String!, $name: String!, $number: Int!) {
			repository(owner: $owner, name: $name) { pullRequest(number: $number) { closingIssuesReferences(first: 10) { nodes { number } } } }
		}' --jq '.data.repository.pullRequest.closingIssuesReferences.nodes[].number'
	jq -r '.body // ""' "$out/pr.json" \
		| grep -oiE '(close[sd]?|fix(e[sd])?|resolve[sd]?|refs?|part of)[[:space:]]+#[0-9]+' \
		| grep -oE '[0-9]+$' || true
} | sort -un | head -5 | while read -r issue; do
	gh issue view "$issue" --repo "$repo" --json number,title,body,state,comments \
		> "$out/issues/$issue.json" 2>/dev/null || rm -f "$out/issues/$issue.json"
done

reviews=$(gh api --paginate "repos/$repo/pulls/$pr/reviews" --jq '.[]' \
	| jq -s --arg bot "$bot" '[.[] | select(.user.login == $bot or .user.login == ($bot + "[bot]"))
		| {id, state, body, commit_id, submitted_at}]')

threads=$(gh api graphql --paginate -F owner="${repo%%/*}" -F name="${repo##*/}" -F number="$pr" -f query='
	query($owner: String!, $name: String!, $number: Int!, $endCursor: String) {
		repository(owner: $owner, name: $name) {
			pullRequest(number: $number) {
				reviewThreads(first: 100, after: $endCursor) {
					pageInfo { hasNextPage endCursor }
					nodes {
						id isResolved isOutdated path line
						comments(first: 50) { nodes { databaseId author { login } body createdAt } }
					}
				}
			}
		}
	}' --jq '.data.repository.pullRequest.reviewThreads.nodes[]' \
	| jq -s --arg bot "$bot" '[.[] | select(.comments.nodes[0].author.login == $bot or .comments.nodes[0].author.login == ($bot + "[bot]"))
		| {id, isResolved, isOutdated, path, line, comments: [.comments.nodes[] | {id: .databaseId, author: .author.login, body}]}]')

jq -n --argjson reviews "$reviews" --argjson threads "$threads" '{reviews: $reviews, threads: $threads}' > "$out/prior.json"
