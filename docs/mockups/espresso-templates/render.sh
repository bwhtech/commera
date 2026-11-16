#!/usr/bin/env bash
# Renders every email (desktop + mobile) and every PDF into out/. Run from anywhere.
set -euo pipefail
cd "$(dirname "$0")"
export PATH=/home/frappe/.nvm/versions/node/v24.12.0/bin:$PATH
PYTHON="/home/frappe/frappe-bench/env/bin/python -W ignore"
export PYTHONPATH="$PWD/.pylib"

npx tsx render.tsx "$@"
./shoot_mobile.sh
$PYTHON trim_shots.py out/emails/*.png
$PYTHON render_pdf.py
