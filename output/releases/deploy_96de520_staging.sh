#!/usr/bin/env bash
set -euo pipefail

release_code="96de520"
active_module="/home/hongyi-jig-erp/odoo/staging_overrides/new_hongyijig_custom"
package_path="/home/hongyi-jig-erp/releases/incoming/Hongyi_Odoo_SSeries_96de520.tar.gz"
expected_sha="98cec0f6d6c897b058ad61e2b18e80ae3d1a077b3f48e6639dd34263e55594d2"
expected_active_source_sha="5f3bbb9619364432a8368b430b9952fd5153af5e27e183ebbf64fcf099354e94"
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

restore_database() {
    export HJIG_DATABASE_DUMP="${database_dump}"
    "${odoo_python}" - <<'PY'
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
subprocess.run(["dropdb", *connection, "--if-exists", database], env=environment, check=True)
subprocess.run(["createdb", *connection, database], env=environment, check=True)
subprocess.run(
    ["pg_restore", *connection, "--no-owner", "-d", database, os.environ["HJIG_DATABASE_DUMP"]],
    env=environment,
    check=True,
)
PY
}

rollback_on_error() {
    failure_code=$?
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
        restore_database
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
test -f "${active_module}/__manifest__.py"
test -d "${filestore}"
test -f "${package_path}"
test ! -e "${rollback_root}"
test ! -e "${failed_root}"
printf '%s  %s\n' "${expected_sha}" "${package_path}" | sha256sum --check --status
grep -q "0 failed, 0 error(s) of 168 tests" "/home/hongyi-jig-erp/releases/work/${release_code}/post_install_tests.log"
grep -q "SSERIES_WORKFLOW_PASS" "/home/hongyi-jig-erp/releases/work/${release_code}/sseries_validation.log"
grep -q "'version': '19.0.3.11.4'" "${active_module}/__manifest__.py"
active_source_sha="$(find "${active_module}" -type f ! -path '*/__pycache__/*' ! -name '*.pyc' -print0 | sort -z | xargs -0 sha256sum | sha256sum | awk '{print $1}')"
test "${active_source_sha}" = "${expected_active_source_sha}"

mkdir -p "${rollback_root}" "${frozen_root}"
cp "${package_path}" "${frozen_root}/"
tar -xzf "${package_path}" -C "${candidate_root}"
grep -q "'version': '19.0.3.12.0'" "${candidate_root}/new_hongyijig_custom/__manifest__.py"

export HJIG_DATABASE_DUMP="${database_dump}"
"${odoo_python}" - <<'PY'
import configparser
import os
import subprocess

config = configparser.ConfigParser()
config.read("/etc/odoo.conf")
options = config["options"]
environment = os.environ.copy()
environment["PGPASSWORD"] = options.get("db_password", "")
subprocess.run(
    [
        "pg_dump",
        "-h", options.get("db_host", "localhost"),
        "-p", options.get("db_port", "5432"),
        "-U", options.get("db_user", "hongyijig"),
        "-Fc", "-f", os.environ["HJIG_DATABASE_DUMP"],
        "HongyijigTech_10Feb",
    ],
    env=environment,
    check=True,
)
PY

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

sudo -n /usr/bin/systemctl is-active odoo.service >/dev/null
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
required_models = {
    "hjig.sseries.intake.submission",
    "hjig.sseries.intake.project",
    "hjig.sseries.intake.component",
    "hjig.sseries.case",
    "hjig.sseries.document.template",
    "hjig.sseries.artifact",
    "hjig.sseries.b0.handover",
    "hjig.programme.run",
    "hjig.portfolio.guard",
    "hjig.sourcebridge.engagement",
}
missing = sorted(name for name in required_models if name not in env)
if missing:
    raise RuntimeError(f"Missing governed models: {missing}")
for xmlid in (
    "new_hongyijig_custom.group_hjig_sseries_user",
    "new_hongyijig_custom.group_hjig_sseries_manager",
    "new_hongyijig_custom.menu_hjig_sseries",
    "new_hongyijig_custom.menu_hjig_my_governed_work",
    "new_hongyijig_custom.action_hjig_sseries_cases",
    "new_hongyijig_custom.action_hjig_my_governed_work",
):
    if not env.ref(xmlid, raise_if_not_found=False):
        raise RuntimeError(f"Missing preserved/new UI authority: {xmlid}")
submission_count = env["hjig.sseries.intake.submission"].search_count([])
case_count = env["hjig.sseries.case"].search_count([])
if env["hjig.sseries.document.template"].search_count([]) != 22:
    raise RuntimeError("Unexpected controlled S-Series document-template count")
for field_name in (
    "hjig_programme_activation_state",
    "hjig_programme_run_ids",
    "hjig_authorized_user_ids",
):
    if field_name not in env["project.project"]._fields:
        raise RuntimeError(f"Missing preserved project field: {field_name}")
Master = env["hjig.governance.artifact.master"]
sops = Master.search([("code", "in", [f"SOP-{number:03d}" for number in range(1, 15)])])
if len(sops) != 14 or sops.filtered(lambda item: not item.ai_reference_ready):
    raise RuntimeError("Preserved B-Series SOP guidance is incomplete")
module = env["ir.module.module"].search([("name", "=", "new_hongyijig_custom")], limit=1)
if module.installed_version != "19.0.3.12.0":
    raise RuntimeError(f"Unexpected installed version: {module.installed_version}")
print(
    "STAGING_SSERIES_WORKFLOW_PASS version=19.0.3.12.0 "
    f"submissions={submission_count} cases={case_count} templates=22 bseries_preserved=true"
)
env.cr.rollback()
PY
grep -q "STAGING_SSERIES_WORKFLOW_PASS" "${postcheck_log}"

grep -q "'version': '19.0.3.12.0'" "${active_module}/__manifest__.py"
sudo -n /usr/bin/systemctl start odoo.service
test "$(systemctl is-active odoo.service)" = "active"
test "$(systemctl is-active odoo-production.service)" = "active"
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
echo "HJIG_STAGING_UPGRADE_SUCCESS release=${release_code} version=19.0.3.12.0 rollback=${rollback_root} http=${http_code} production=untouched"

