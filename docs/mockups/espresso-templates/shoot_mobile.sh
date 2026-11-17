#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PATH=/home/frappe/.nvm/versions/node/v24.12.0/bin:$PATH
export AGENT_BROWSER_ARGS=--disable-gpu-vsync

agent-browser set viewport 390 4400 2 >/dev/null
for html in out/emails/*.html; do
	name=$(basename "$html" .html)
	agent-browser open "file://$PWD/$html" >/dev/null
	agent-browser wait 1500 >/dev/null
	overflow=$(agent-browser eval "document.documentElement.scrollWidth - window.innerWidth")
	echo "$name horizontal overflow: ${overflow}px"
	agent-browser screenshot "out/emails/$name-mobile.png" >/dev/null
done
agent-browser close >/dev/null
