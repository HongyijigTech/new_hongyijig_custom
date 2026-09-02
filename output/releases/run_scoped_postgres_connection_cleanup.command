#!/usr/bin/env bash
set -euo pipefail

ssh -tt \
  -i /Users/jagdeepkhattar/.ssh/hjig_sseries_staging \
  -o IdentitiesOnly=yes \
  hongyi-jig-erp@10.10.71.37 \
  'sudo -u postgres /usr/bin/psql -d postgres -c "WITH targets AS (SELECT pid FROM pg_stat_activity WHERE datname LIKE '\''hongyijig_sseries_test_%'\'' AND state = '\''idle'\'' AND pid <> pg_backend_pid()) SELECT count(*) AS terminated FROM targets WHERE pg_terminate_backend(pid);"'

echo "Scoped S-Series disposable-test connection cleanup finished. Return to Codex and type done."
read -r -p "Press Enter to close this window."
