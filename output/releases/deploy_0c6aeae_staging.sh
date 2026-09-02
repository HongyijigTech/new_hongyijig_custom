#!/usr/bin/env bash
set -euo pipefail

release_code="0c6aeae"
active_module="/home/hongyi-jig-erp/odoo/staging_overrides/new_hongyijig_custom"
package_path="/home/hongyi-jig-erp/releases/incoming/Hongyi_Odoo_SSeries_0c6aeae.tar.gz"
expected_sha="5f61eff21d1dd0d55568702479de72056e909c106d6785009ab07ba27750693f"
expected_active_source_sha="16f84c19b952899806e4ba132e904d773185188d3bb6d1d522d96d7e4f716be0"
release_stamp="$(date +%Y%m%d_%H%M%S)"
rollback_root="/home/hongyi-jig-erp/releases/rollback/${release_code}_predeploy_${release_stamp}"
failed_root="/home/hongyi-jig-erp/releases/rollback/${release_code}_failed_${release_stamp}"
frozen_root="/home/hongyi-jig-erp/releases/frozen/${release_code}"
candidate_root="$(mktemp -d /home/hongyi-jig-erp/odoo/staging_overrides/.hjig-${release_code}-XXXXXX)"
upgrade_log="${frozen_root}/staging-upgrade.log"
postcheck_log="${frozen_root}/staging-postcheck.log"
database_dump="${rollback_root}/HongyijigTech_10Feb_predeploy.dump"
filestore="/home/hongyi-jig-erp/.local/share/Odoo/filestore/HongyijigTech_10Feb"
filestore_backup="${rollback_root}/HongyijigTech_10Feb_filestore_predeploy.tar.gz"
odoo_python="/home/hongyi-jig-erp/odoo/venv19/bin/python3"
odoo_bin="/home/hongyi-jig-erp/odoo/odoo-bin"
odoo_config="/etc/odoo.conf"
addons_path="/home/hongyi-jig-erp/odoo/staging_overrides,/home/hongyi-jig-erp/odoo/odoo/addons,/home/hongyi-jig-erp/odoo/addons,/home/hongyi-jig-erp/odoo/enterprise,/home/hongyi-jig-erp/odoo/hongyijigTech_custom"
deployment_started=0
rollback_in_progress=0

database_action() {
    local action="$1"
    HJIG_DATABASE_ACTION="${action}" HJIG_DATABASE_DUMP="${database_dump}" "${odoo_python}" - <<'PY'
import configparser
import os
import subprocess

config = configparser.ConfigParser()
config.read("/etc/odoo.conf")
options = config["options"]
environment = os.environ.copy()
environment["PGPASSWORD"] = options.get("db_password", "")
connection = [
    "-h", options.get("db_host", "localhost"),
    "-p", options.get("db_port", "5432"),
    "-U", options.get("db_user", "hongyijig"),
]
database = "HongyijigTech_10Feb"
dump_path = os.environ["HJIG_DATABASE_DUMP"]
if os.environ["HJIG_DATABASE_ACTION"] == "backup":
    subprocess.run(["pg_dump", *connection, "-Fc", "-f", dump_path, database], env=environment, check=True)
else:
    subprocess.run(["dropdb", *connection, "--if-exists", database], env=environment, check=True)
    subprocess.run(["createdb", *connection, database], env=environment, check=True)
    subprocess.run(["pg_restore", *connection, "--no-owner", "-d", database, dump_path], env=environment, check=True)
PY
}

rollback_on_error() {
    local failure_code=$?
    trap - ERR
    if test "${rollback_in_progress}" -eq 1; then
        exit "${failure_code}"
    fi
    rollback_in_progress=1
    set +e
    if test "${deployment_started}" -eq 1; then
        mkdir -p "${failed_root}"
        sudo -n /usr/bin/systemctl stop odoo.service
        if test -d "${rollback_root}/active_module"; then
            if test -d "${active_module}"; then
                mv "${active_module}" "${failed_root}/candidate_module"
            fi
            mv "${rollback_root}/active_module" "${active_module}"
        fi
        database_action restore
        if test -d "${filestore}"; then
            mv "${filestore}" "${failed_root}/filestore_after_failure"
        fi
        tar -xzf "${filestore_backup}" -C "$(dirname "${filestore}")"
        sudo -n /usr/bin/systemctl start odoo.service
        test "$(systemctl is-active odoo.service)" = "active"
        test "$(systemctl is-active odoo-production.service)" = "active"
        echo "HJIG_STAGING_UPGRADE_ROLLED_BACK release=${release_code} code=${failure_code} rollback=${rollback_root}"
    fi
    exit "${failure_code}"
}
trap rollback_on_error ERR

test "$(systemctl is-active odoo.service)" = "active"
test "$(systemctl is-active odoo-production.service)" = "active"
test "$(systemctl is-active clamav-daemon.service)" = "active"
test "$(systemctl is-active clamav-freshclam.service)" = "active"
test -x /usr/bin/clamdscan
test -f "${active_module}/__manifest__.py"
test -d "${filestore}"
test -f "${package_path}"
printf '%s  %s\n' "${expected_sha}" "${package_path}" | sha256sum --check --status
grep -q "0 failed, 0 error(s) of 201 tests" "/home/hongyi-jig-erp/releases/work/${release_code}/post_install_tests.log"
grep -q "SSERIES_AUTHORITY_PASS" "/home/hongyi-jig-erp/releases/work/${release_code}/sseries_validation.log"
grep -q "'version': '19.0.3.21.0'" "${active_module}/__manifest__.py"
active_source_sha="$(find "${active_module}" -type f ! -path '*/__pycache__/*' ! -name '*.pyc' -print0 | sort -z | xargs -0 sha256sum | sha256sum | awk '{print $1}')"
test "${active_source_sha}" = "${expected_active_source_sha}"

mkdir -p "${rollback_root}" "${frozen_root}"
cp "${package_path}" "${frozen_root}/"
tar -xzf "${package_path}" -C "${candidate_root}"
grep -q "'version': '19.0.3.22.0'" "${candidate_root}/new_hongyijig_custom/__manifest__.py"

database_action backup
tar -czf "${filestore_backup}" -C "$(dirname "${filestore}")" "$(basename "${filestore}")"
cp "${odoo_config}" "${rollback_root}/odoo.conf"
cp /etc/systemd/system/odoo.service "${rollback_root}/odoo.service"
tar -czf "${rollback_root}/new_hongyijig_custom_predeploy.tar.gz" \
    -C "$(dirname "${active_module}")" "$(basename "${active_module}")"
sha256sum \
    "${database_dump}" \
    "${filestore_backup}" \
    "${rollback_root}/odoo.conf" \
    "${rollback_root}/odoo.service" \
    "${rollback_root}/new_hongyijig_custom_predeploy.tar.gz" \
    > "${rollback_root}/SHA256SUMS"
sha256sum --check "${rollback_root}/SHA256SUMS"

sudo -n /usr/bin/systemctl stop odoo.service
deployment_started=1
test "$(systemctl is-active odoo-production.service)" = "active"
mv "${active_module}" "${rollback_root}/active_module"
mv "${candidate_root}/new_hongyijig_custom" "${active_module}"
rmdir "${candidate_root}"

"${odoo_python}" "${odoo_bin}" \
    -c "${odoo_config}" \
    -d HongyijigTech_10Feb \
    -u new_hongyijig_custom \
    --stop-after-init \
    --no-http \
    --workers=0 \
    --max-cron-threads=0 \
    --log-level=info \
    --logfile="${upgrade_log}"

"${odoo_python}" "${odoo_bin}" shell \
    -c "${odoo_config}" \
    -d HongyijigTech_10Feb \
    --no-http \
    --addons-path="${addons_path}" \
    > "${postcheck_log}" 2>&1 <<'PY'
module = env["ir.module.module"].search([("name", "=", "new_hongyijig_custom")], limit=1)
if module.installed_version != "19.0.3.22.0":
    raise RuntimeError(f"Unexpected installed version: {module.installed_version}")

Template = env["hjig.sseries.document.template"]
if Template.search_count([]) != 24:
    raise RuntimeError("Unexpected controlled S-Series document-template count")
activation_codes = {
    "S4-NDA", "S4-INTRODUCED-PARTY-NOTICE", "S4-DIRECT-ENGAGEMENT-CONSENT",
    "S4-ACCEPTANCE", "S5-ORDER-PUNCH", "S5-PROFORMA", "S5-PAYMENT-EVIDENCE",
    "S5-TAX-INVOICE", "S6-TEAM-HANDOVER", "S6-CHINA-HANDOVER",
    "S6-SUPPLIER-RFQ-EN", "S6-SUPPLIER-RFQ-ZH", "B0-HANDOVER-MANIFEST",
}
activation = Template.search([("code", "in", sorted(activation_codes))])
if set(activation.mapped("code")) != activation_codes:
    raise RuntimeError("Activation authority registry is incomplete")
approved = activation.filtered("approved_for_internal_uat_generation")
if approved.mapped("code") != ["S5-PROFORMA"]:
    raise RuntimeError("Only S5-PROFORMA may have internal-UAT generation authority")
if activation.filtered("user_final_approval"):
    raise RuntimeError("Pending activation records must not have user final approval")
if activation.filtered("customer_issue_allowed") or activation.filtered("supplier_issue_allowed"):
    raise RuntimeError("Pending activation records must remain fail-closed for external issue")
if (activation - approved).filtered("template_visual_qa_verified"):
    raise RuntimeError("Pending candidates must not be visual-QA verified")
if (activation - approved).filtered("template_content_qa_verified"):
    raise RuntimeError("Pending candidates must not be content-QA verified")
if approved.template_visual_qa_verified or approved.template_content_qa_verified:
    raise RuntimeError("PI template QA gates must remain separate from internal-UAT authority")
if Template.search([("code", "=", "S5-PAYMENT-EVIDENCE")], limit=1).rendering_status != "blocked":
    raise RuntimeError("Payment evidence must remain blocked without a master")
if Template.search([("code", "=", "S5-TAX-INVOICE")], limit=1).rendering_status != "blocked":
    raise RuntimeError("Tax invoice must remain at the Tally boundary")

Artifact = env["hjig.sseries.artifact"]
for field_name in (
    "template_authority_status", "template_generation_allowed",
    "render_engine_version", "render_source_digest", "rendered_page_count", "render_manifest_json",
):
    if field_name not in Artifact._fields:
        raise RuntimeError(f"Missing controlled artifact field: {field_name}")
for method_name in ("action_verify_visual_qa", "action_verify_content_qa", "action_verify_qa"):
    if not hasattr(Artifact, method_name):
        raise RuntimeError(f"Missing governed QA action: {method_name}")

cases = env["hjig.sseries.case"].search([])
if cases.filtered(lambda item: not item.lead_id):
    raise RuntimeError("CRM spine reconciliation left an S-Series case without an opportunity")
for submission in cases.mapped("submission_id"):
    if len(submission.case_ids.mapped("lead_id")) != 1:
        raise RuntimeError("One website submission must map to exactly one CRM opportunity")
menu = env.ref("new_hongyijig_custom.menu_hjig_sseries")
if menu.group_ids != env.ref("base.group_no_one"):
    raise RuntimeError("Separate S-Series employee menu is not hidden")
Master = env["hjig.governance.artifact.master"]
sops = Master.search([("code", "in", [f"SOP-{number:03d}" for number in range(1, 15)])])
if len(sops) != 14 or sops.filtered(lambda item: not item.ai_reference_ready):
    raise RuntimeError("Preserved B-Series SOP guidance is incomplete")
print(
    "STAGING_SSERIES_AUTHORITY_PASS version=19.0.3.22.0 templates=24 activation_records=13 "
    f"submissions={env['hjig.sseries.intake.submission'].search_count([])} cases={len(cases)} "
    "only_pi_internal_uat=true one_crm_spine=true bseries_preserved=true"
)
env.cr.rollback()
PY
grep -q "STAGING_SSERIES_AUTHORITY_PASS" "${postcheck_log}"

grep -q "'version': '19.0.3.22.0'" "${active_module}/__manifest__.py"
sudo -n /usr/bin/systemctl start odoo.service
test "$(systemctl is-active odoo.service)" = "active"
test "$(systemctl is-active odoo-production.service)" = "active"
test "$(systemctl is-active clamav-daemon.service)" = "active"
test "$(systemctl is-active clamav-freshclam.service)" = "active"
http_code="000"
for startup_attempt in $(seq 1 30); do
    http_code="$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:8070/web/login || true)"
    if test "${http_code}" = "200" -o "${http_code}" = "303"; then
        break
    fi
    sleep 1
done
test "${http_code}" = "200" -o "${http_code}" = "303"
if grep -Eq "ERROR|CRITICAL" "${upgrade_log}"; then
    exit 1
fi
deployment_started=0
trap - ERR
echo "HJIG_STAGING_UPGRADE_SUCCESS release=${release_code} version=19.0.3.22.0 rollback=${rollback_root} http=${http_code} production=untouched"
