#!/usr/bin/env bash
# shellcheck disable=SC2029
# Usage: pr-devbox.sh up <pr number> <branch> <dashboard assets .tgz>   prints the box as JSON
#        pr-devbox.sh down <pr number>
# Needs BENCHSPACE_API_KEY, BENCHSPACE_API_SECRET, and an ssh key that DEVBOX_HOST accepts.
set -euo pipefail

benchspace="${BENCHSPACE_URL:-https://boxes.buildwithhussain.com}"
host="${DEVBOX_HOST:-root@95.217.148.61}"
template="${DEVBOX_TEMPLATE:-ERPNext v16}"
server="${DEVBOX_SERVER:-Prod-01}"
max_boxes="${DEVBOX_MAX_PR_BOXES:-2}"
box_memory=$((4 * 1024 * 1024 * 1024))
site="dev.localhost"
ssh_options=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 -o ServerAliveInterval=30)

api() {
	local method="$1" path="$2"
	shift 2
	curl -sfS -X "$method" -H "Authorization: token $BENCHSPACE_API_KEY:$BENCHSPACE_API_SECRET" \
		-H "Accept: application/json" "$@" "$benchspace/api/$path"
}

find_box() {
	api GET "resource/Dev%20Box" -G \
		--data-urlencode "filters=[[\"title\",\"=\",\"commera PR #$1\"],[\"status\",\"!=\",\"deleted\"]]" \
		--data-urlencode 'fields=["name","status"]' | jq -r '.data[0].name // empty'
}

box_status() {
	api GET "resource/Dev%20Box/$1" | jq -r '.data.status'
}

wait_for_status() {
	local box="$1" wanted="$2" status=""
	for _ in $(seq 1 90); do
		status=$(box_status "$box")
		[ "$status" = "$wanted" ] && return 0
		[ "$status" = "error" ] && { echo "box $box failed to start" >&2; return 1; }
		sleep 10
	done
	echo "box $box is still $status after 15 minutes" >&2
	return 1
}

check_capacity() {
	local boxes
	boxes=$(api GET "resource/Dev%20Box" -G \
		--data-urlencode 'filters=[["title","like","commera PR #%"],["status","not in",["deleted","stopped"]]]' \
		--data-urlencode 'fields=["name"]' | jq '.data | length')
	if [ "$boxes" -ge "$max_boxes" ]; then
		echo "$boxes PR boxes are running already; the limit is $max_boxes. Close a PR or delete its box first." >&2
		return 1
	fi
	read -r high current < <(ssh "${ssh_options[@]}" "$host" \
		"systemctl show devbox-agent -p MemoryHigh -p MemoryCurrent --value | tr '\n' ' '")
	if [ "$high" != "infinity" ] && [ $((high - current)) -lt "$box_memory" ]; then
		echo "the devbox host has less than 4 GiB left under its memory limit; a new box would throttle every box" >&2
		return 1
	fi
}

box_ip() {
	ssh "${ssh_options[@]}" "$host" "curl -s http://localhost:2019/config/apps/http/servers/srv0/routes" \
		| jq -r --arg host "$1.site" '[.[] | select(any(.match[]?.host[]?; startswith($host))) | .. | .dial? // empty][0] | split(":")[0]'
}

in_box() {
	ssh "${ssh_options[@]}" -J "$host" "frappe@$ip" "bash -lc 'source ~/.nvm/nvm.sh 2>/dev/null; cd ~/frappe-bench && $1'"
}

as_root() {
	ssh "${ssh_options[@]}" "$host" "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i /opt/devbox/agent/fc_key root@$ip '$1'"
}

up() {
	local pr="$1" branch="$2" assets="$3" box
	box=$(find_box "$pr")
	if [ -z "$box" ]; then
		check_capacity
		box=$(jq -n --arg title "commera PR #$pr" --arg server "$server" --arg template "$template" \
			'{title: $title, server: $server, devbox_template: $template}' \
			| api POST "resource/Dev%20Box" -H "Content-Type: application/json" --data @- | jq -r '.data.name')
	elif [ "$(box_status "$box")" = "stopped" ]; then
		api POST "method/run_doc_method" --data-urlencode "dt=Dev Box" --data-urlencode "dn=$box" \
			--data-urlencode "method=start_box" > /dev/null
	fi
	wait_for_status "$box" active >&2

	ip=$(box_ip "$box")
	[ -n "$ip" ] || { echo "could not find the internal address of box $box" >&2; return 1; }

	local public_key
	public_key=$(ssh-add -L | head -1)
	as_root "date -u -s \"$(date -u '+%Y-%m-%d %H:%M:%S')\" > /dev/null
		mkdir -p /home/frappe/.ssh && touch /home/frappe/.ssh/authorized_keys
		grep -qxF \"$public_key\" /home/frappe/.ssh/authorized_keys || echo \"$public_key\" >> /home/frappe/.ssh/authorized_keys
		chown -R frappe:frappe /home/frappe/.ssh && chmod 700 /home/frappe/.ssh && chmod 600 /home/frappe/.ssh/authorized_keys" >&2

	in_box "git -C apps/frappe pull -q && bench setup requirements --python > /dev/null" >&2
	for app in bwh_payments bwh_shipping; do
		in_box "test -d apps/$app || bench get-app https://github.com/bwhtech/$app" >&2
	done
	in_box "if test -d apps/commera; then git -C apps/commera fetch -q --depth 1 https://github.com/bwhtech/commera $branch && git -C apps/commera checkout -q -f -B pr FETCH_HEAD; else bench get-app https://github.com/bwhtech/commera --branch $branch; fi" >&2
	in_box "installed=\$(bench --site $site list-apps); for app in erpnext bwh_payments bwh_shipping commera; do echo \"\$installed\" | grep -qw \$app || bench --site $site install-app \$app; done" >&2
	in_box "bench --site $site migrate" >&2
	in_box "test -f ~/.pr_seeded || { bench --site $site execute commera.install.before_tests && bench --site $site execute commera.install_summer_demo.install_summer_demo --kwargs \"{\\\"currency\\\": \\\"INR\\\"}\" && touch ~/.pr_seeded; }" >&2

	in_box "tar -xzf - -C apps/commera && ln -sfn ../../apps/commera/commera/public sites/assets/commera" < "$assets" >&2
	as_root "supervisorctl restart all > /dev/null" >&2

	api GET "resource/Dev%20Box/$box" | jq '.data | {name, site_url, code_url}'
}

down() {
	local box
	box=$(find_box "$1")
	[ -n "$box" ] || return 0
	api POST "method/run_doc_method" --data-urlencode "dt=Dev Box" --data-urlencode "dn=$box" \
		--data-urlencode "method=delete_box" > /dev/null
	echo "deleted box $box"
}

case "${1:-}" in
up) up "$2" "$3" "$4" ;;
down) down "$2" ;;
*) echo "usage: pr-devbox.sh up <pr> <branch> <assets.tgz> | down <pr>" >&2; exit 2 ;;
esac
