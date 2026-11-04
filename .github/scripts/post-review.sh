#!/usr/bin/env bash
# shellcheck disable=SC2016
# Adapted from frappe/frappe .github/workflows/post-review.yml (MIT).
# Usage: post-review.sh <pr number> <review.json> <bot login>
# Needs GH_TOKEN and GITHUB_REPOSITORY. REVIEW_COMMIT pins inline comments to the reviewed commit.
# DRY_RUN=1 prints each write instead of sending it.
set -euo pipefail

pr="$1"
review="$2"
bot="${3%\[bot\]}"
repo="$GITHUB_REPOSITORY"
work=$(mktemp -d)

write() {
	local method="$1" path="$2" input="${3:-}"
	if [ -n "${DRY_RUN:-}" ]; then
		echo "DRY_RUN $method $path ${input:+$(jq -c . "$input")}"
		return 0
	fi
	if [ -n "$input" ]; then
		gh api -X "$method" "$path" --input "$input" --jq '.html_url // .id // empty'
	else
		gh api -X "$method" "$path" --jq '.html_url // .id // empty'
	fi
}

is_bot='(. == $bot or . == ($bot + "[bot]"))'

jq -e '
	(.event == "COMMENT" or .event == "REQUEST_CHANGES")
	and (.body | type == "string")
	and ((.comments // []) | type == "array" and all((.path | type == "string") and (.line | type == "number") and (.body | type == "string" and length > 0)))
	and ((.replies // []) | type == "array" and all((.in_reply_to | type == "number") and (.body | type == "string" and length > 0)))
	and ((.resolve // []) | type == "array" and all(type == "string" and startswith("PRRT_")))
	and (.dismiss == null or (.event == "COMMENT" and (.dismiss.message | type == "string" and length > 0) and (.dismiss.reviews | type == "array" and all(type == "number"))))
' "$review" > /dev/null || { echo "review.json does not match the format in .github/review/method.md" >&2; exit 1; }

if [ "$(jq -r '(.body | length) + ((.comments // []) | length)' "$review")" != "0" ]; then
	jq --arg commit "${REVIEW_COMMIT:-}" '{event, body, comments: [(.comments // [])[] | {path, line, side: "RIGHT", body}]}
		+ (if $commit == "" then {} else {commit_id: $commit} end)' "$review" > "$work/payload.json"

	gh api --paginate "repos/$repo/pulls/$pr/reviews" --jq '.[]' \
		| jq -s --arg bot "$bot" "[.[] | select(.user.login | $is_bot) | {state, body}]" > "$work/posted.json"
	if jq -e --slurpfile posted "$work/posted.json" '. as $new | {COMMENT: "COMMENTED", REQUEST_CHANGES: "CHANGES_REQUESTED"}[$new.event] as $state
		| $posted[0] | any(.state == $state and .body == $new.body)' "$work/payload.json" > /dev/null; then
		echo "skipped the review: the bot already posted it" >&2
	elif ! write POST "repos/$repo/pulls/$pr/reviews" "$work/payload.json"; then
		jq '.body += ([.comments[] | "\n\n**\(.path):\(.line)**\n\n\(.body)"] | join("")) | .comments = []' \
			"$work/payload.json" > "$work/folded.json"
		echo "an inline comment was rejected; posting the findings in the review body" >&2
		write POST "repos/$repo/pulls/$pr/reviews" "$work/folded.json"
	fi
fi

if [ "$(jq '(.replies // []) | length' "$review")" != "0" ]; then
	gh api --paginate "repos/$repo/pulls/$pr/comments" --jq '.[]' \
		| jq -s --arg bot "$bot" "[.[] | select((.user.login | $is_bot) and .in_reply_to_id != null) | {in_reply_to: .in_reply_to_id, body}]" \
		> "$work/replies.json"
	jq -c --slurpfile posted "$work/replies.json" '(.replies // [])[] | {in_reply_to, body} | select(. as $reply | $posted[0] | any(. == $reply) | not)' "$review" \
		| while read -r reply; do
			printf '%s' "$reply" > "$work/reply.json"
			write POST "repos/$repo/pulls/$pr/comments" "$work/reply.json"
		done
fi

if [ "$(jq '(.resolve // []) | length' "$review")" != "0" ]; then
	gh api graphql --paginate -F owner="${repo%%/*}" -F name="${repo##*/}" -F number="$pr" -f query='
		query($owner: String!, $name: String!, $number: Int!, $endCursor: String) {
			repository(owner: $owner, name: $name) { pullRequest(number: $number) {
				reviewThreads(first: 100, after: $endCursor) { pageInfo { hasNextPage endCursor }
					nodes { id isResolved comments(first: 1) { nodes { author { login } } } } } } }
		}' --jq '.data.repository.pullRequest.reviewThreads.nodes[]' \
		| jq -r --arg bot "$bot" "select(.isResolved == false and (.comments.nodes[0].author.login | $is_bot)) | .id" \
		> "$work/own-threads.txt"
	jq -r '.resolve[]' "$review" | while read -r thread; do
		if ! grep -qxF "$thread" "$work/own-threads.txt"; then
			echo "skipped $thread: not an open thread of the bot on this PR" >&2
		elif [ -n "${DRY_RUN:-}" ]; then
			echo "DRY_RUN resolve $thread"
		else
			gh api graphql -f id="$thread" -f query='mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { isResolved } } }' \
				--jq '"resolved \(.data.resolveReviewThread.thread.isResolved)"'
		fi
	done
fi

if jq -e '.dismiss != null' "$review" > /dev/null; then
	jq '{message: .dismiss.message, event: "DISMISS"}' "$review" > "$work/dismissal.json"
	gh api --paginate "repos/$repo/pulls/$pr/reviews" --jq '.[]' \
		| jq -r --arg bot "$bot" "select((.user.login | $is_bot) and .state == \"CHANGES_REQUESTED\") | .id" \
		> "$work/own-change-requests.txt"
	jq -r '.dismiss.reviews[]' "$review" | while read -r review_id; do
		if grep -qxF "$review_id" "$work/own-change-requests.txt"; then
			write PUT "repos/$repo/pulls/$pr/reviews/$review_id/dismissals" "$work/dismissal.json"
		else
			echo "skipped $review_id: not an open change request of the bot on this PR" >&2
		fi
	done
fi
