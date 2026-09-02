#!/usr/bin/env bash
set -euo pipefail

ssh -tt \
  -i /Users/jagdeepkhattar/.ssh/hjig_sseries_staging \
  -o IdentitiesOnly=yes \
  hongyi-jig-erp@10.10.71.37 \
  'set -eu
   sudo apt-get update
   sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y clamav-daemon clamav-freshclam
   sudo systemctl enable --now clamav-freshclam.service
   sudo systemctl enable --now clamav-daemon.service
   test "$(systemctl is-active clamav-freshclam.service)" = "active"
   test "$(systemctl is-active clamav-daemon.service)" = "active"
   test "$(systemctl is-active odoo.service)" = "active"
   test "$(systemctl is-active odoo-production.service)" = "active"
   /usr/bin/clamdscan --version
   echo "HJIG_CLAMAV_HOST_READY odoo_staging=active odoo_production=active production_data=untouched"'

echo "ClamAV host installation finished. Return to Codex and type done."
read -r -p "Press Enter to close this window."
