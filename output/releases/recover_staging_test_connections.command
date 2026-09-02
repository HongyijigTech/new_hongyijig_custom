#!/bin/bash
set -euo pipefail

ssh -tt -i /Users/jagdeepkhattar/.ssh/hjig_sseries_staging \
  -o StrictHostKeyChecking=accept-new \
  hongyi-jig-erp@10.10.71.37 \
  'sudo systemctl stop odoo.service && sudo -u postgres psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname LIKE '\''hongyijig_sseries_test_%'\'' AND pid <> pg_backend_pid();"; sudo systemctl start odoo.service; systemctl is-active odoo.service; systemctl is-active odoo-production.service'

echo 'HJIG_STAGING_RECOVERED — staging restarted; production check shown above.'
read -r -n 1 -s -p 'Press any key to close'
