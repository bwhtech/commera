#!/usr/bin/env bash
# 390px shots of every stepper card, then trim the empty page below the card.
set -euo pipefail
cd "$(dirname "$0")"
export PATH=/home/frappe/.nvm/versions/node/v24.12.0/bin:$PATH
export AGENT_BROWSER_ARGS=--disable-gpu-vsync
browser="agent-browser --session steppers"

$browser set viewport 390 1200 2 >/dev/null
for html in out/steppers/*-confirmed.html out/steppers/*-shipped.html out/steppers/*-delivered.html; do
	name=$(basename "$html" .html)
	$browser open "file://$PWD/$html" >/dev/null
	$browser wait 1200 >/dev/null
	overflow=$($browser eval "document.documentElement.scrollWidth - window.innerWidth")
	echo "$name overflow ${overflow}px"
	$browser screenshot "out/steppers/$name-mobile.png" >/dev/null
done
$browser close >/dev/null
/home/frappe/frappe-bench/env/bin/python -W ignore trim_shots.py out/steppers/*.png
