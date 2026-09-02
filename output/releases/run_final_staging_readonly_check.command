#!/usr/bin/env bash
set -euo pipefail

# Read-only check only: no module upgrade, database write, restart or production action.
ssh -o ConnectTimeout=15 hongyi@10.10.71.37 'bash -s' <<'REMOTE'
set -euo pipefail
/home/hongyi-jig-erp/odoo/venv19/bin/python3 /home/hongyi-jig-erp/odoo/odoo-bin shell \
  -c /etc/odoo.conf \
  -d HongyijigTech_10Feb \
  --no-http \
  --addons-path=/home/hongyi-jig-erp/odoo/staging_overrides,/home/hongyi-jig-erp/odoo/odoo/addons,/home/hongyi-jig-erp/odoo/addons,/home/hongyi-jig-erp/odoo/enterprise,/home/hongyi-jig-erp/odoo/hongyijigTech_custom <<'PY'
module = env['ir.module.module'].search([('name', '=', 'new_hongyijig_custom')], limit=1)
case = env['hjig.sseries.case'].search([('name', '=', 'S/2026/000003')], limit=1)
assert module.installed_version == '19.0.3.28.0', module.installed_version
assert case and case.stage == 'b0_released', case.stage if case else 'missing'
assert case.b0_manifest_id and case.b0_manifest_id.integrity_status == 'pass'
print('HJIG_FINAL_STAGING_READONLY_PASS version=%s case=%s b0=%s integrity=%s' % (module.installed_version, case.name, case.b0_manifest_id.name, case.b0_manifest_id.integrity_status))
PY
printf 'STAGING_SERVICE='; systemctl is-active odoo.service
printf 'PRODUCTION_SERVICE='; systemctl is-active odoo-production.service
REMOTE
