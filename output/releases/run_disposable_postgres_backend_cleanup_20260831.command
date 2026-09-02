#!/usr/bin/env bash
set -euo pipefail

ssh -tt \
  -i /Users/jagdeepkhattar/.ssh/hjig_sseries_staging \
  -o IdentitiesOnly=yes \
  hongyi-jig-erp@10.10.71.37 \
  'set -eu
   python3 /tmp/cleanup_disposable_postgres_backends_20260831.py --execute
   sleep 2
   test "$(systemctl is-active odoo.service)" = "active"
   test "$(systemctl is-active odoo-production.service)" = "active"
   test "$(systemctl is-active clamav-daemon.service)" = "active"
   test "$(systemctl is-active clamav-freshclam.service)" = "active"
   echo "HJIG_DISPOSABLE_BACKEND_WINDOW_CLEARED live_databases_untouched=true production_untouched=true"'

echo "Disposable PostgreSQL backend cleanup finished. Return to Codex and type done."
read -r -p "Press Enter to close this window."
