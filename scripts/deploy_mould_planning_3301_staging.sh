#!/usr/bin/env bash
set -euo pipefail

archive=/tmp/new_hongyijig_custom_19.0.3.30.2_a02a0d9.tar.gz
expected_sha=ad2c21ecc060d86d499feeeb58232576ca4a0f76c46bb0791548ec6f37c9b048
database=HongyijigTech_10Feb
target=/home/hongyi-jig-erp/odoo/staging_overrides/new_hongyijig_custom
release_id=mould_planning_3302_$(date +%Y%m%d_%H%M%S)
backup=/home/hongyi-jig-erp/deployment_backups/${release_id}
extract=$(mktemp -d /home/hongyi-jig-erp/deployment_work/${release_id}_extract_XXXXXX)

test "$(sha256sum "$archive" | awk '{print $1}')" = "$expected_sha"
test -d "$target"
test ! -e "$backup"
mkdir -p "$backup"

production_pid_before=$(systemctl show -p MainPID --value odoo-production.service)
tar -czf "$backup/new_hongyijig_custom_pre_3301.tar.gz" -C "$(dirname "$target")" "$(basename "$target")"
sudo -u postgres pg_dump -Fc -d "$database" > "$backup/${database}_pre_3301.dump"
test -s "$backup/${database}_pre_3301.dump"
sha256sum "$backup/new_hongyijig_custom_pre_3301.tar.gz" "$backup/${database}_pre_3301.dump" > "$backup/SHA256SUMS"

tar -xzf "$archive" -C "$extract"
grep -q "19.0.3.30.2" "$extract/new_hongyijig_custom/__manifest__.py"

rollback() {
    status=$?
    if [ "$status" -ne 0 ]; then
        sudo systemctl stop odoo.service || true
        if [ -d "$target" ]; then
            mv "$target" "$backup/failed_3301_source_tree"
        fi
        if [ -d "$backup/previous_source_tree" ]; then
            mv "$backup/previous_source_tree" "$target"
        fi
        sudo systemctl start odoo.service || true
    fi
    exit "$status"
}
trap rollback EXIT

sudo systemctl stop odoo.service
mv "$target" "$backup/previous_source_tree"
mv "$extract/new_hongyijig_custom" "$target"

/home/hongyi-jig-erp/odoo/venv19/bin/python3 /home/hongyi-jig-erp/odoo/odoo-bin \
  -c /etc/odoo.conf -d "$database" \
  --addons-path=/home/hongyi-jig-erp/odoo/staging_overrides,/home/hongyi-jig-erp/odoo/odoo/addons,/home/hongyi-jig-erp/odoo/addons,/home/hongyi-jig-erp/odoo/enterprise,/home/hongyi-jig-erp/odoo/hongyijigTech_custom \
  -u new_hongyijig_custom --stop-after-init --max-cron-threads=0 \
  --logfile="$backup/upgrade.log"

sudo systemctl start odoo.service
sudo systemctl is-active --quiet odoo.service
test "$production_pid_before" = "$(systemctl show -p MainPID --value odoo-production.service)"
curl --fail --silent --show-error --max-time 20 http://127.0.0.1:8070/web/login > "$backup/http_login.html"
! grep -E "ERROR|CRITICAL" "$backup/upgrade.log"

trap - EXIT
echo "MOULD_PLANNING_3302_STAGING_DEPLOYMENT=PASS"
echo "BACKUP_DIR=$backup"
cat "$backup/SHA256SUMS"
