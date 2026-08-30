#!/usr/bin/env bash
set -euo pipefail

release_code="9c7f17f"
package_path="/home/hongyi-jig-erp/releases/incoming/Hongyi_Odoo_SSeries_9c7f17f.tar.gz"
expected_sha="3d9cfb00c7810b085fc2754266d1d12b659688fa754b9a9ca4bd1ea407039c56"
work_root="/home/hongyi-jig-erp/releases/work/${release_code}"
candidate_root="${work_root}/candidate"
source_dump="${work_root}/HongyijigTech_10Feb_source.dump"
test_database="hongyijig_sseries_test_9c7f17f"
test_log="${work_root}/post_install_tests.log"
validation_log="${work_root}/sseries_validation.log"
odoo_python="/home/hongyi-jig-erp/odoo/venv19/bin/python3"
odoo_bin="/home/hongyi-jig-erp/odoo/odoo-bin"
odoo_config="/etc/odoo.conf"
addons_path="${candidate_root},/home/hongyi-jig-erp/odoo/staging_overrides,/home/hongyi-jig-erp/odoo/odoo/addons,/home/hongyi-jig-erp/odoo/addons,/home/hongyi-jig-erp/odoo/enterprise,/home/hongyi-jig-erp/odoo/hongyijigTech_custom"

test "$(systemctl is-active odoo.service)" = "active"
test "$(systemctl is-active odoo-production.service)" = "active"
test -f "${package_path}"
printf '%s  %s\n' "${expected_sha}" "${package_path}" | sha256sum --check --status

mkdir -p "${work_root}"
if test -e "${candidate_root}"; then
    mv "${candidate_root}" "${work_root}/candidate_previous_$(date +%Y%m%d_%H%M%S)"
fi
mkdir -p "${candidate_root}"
tar -xzf "${package_path}" -C "${candidate_root}"
grep -q "'version': '19.0.3.10.0'" "${candidate_root}/new_hongyijig_custom/__manifest__.py"

export HJIG_SOURCE_DUMP="${source_dump}"
export HJIG_TEST_DATABASE="${test_database}"
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
test_database = os.environ["HJIG_TEST_DATABASE"]
source_dump = os.environ["HJIG_SOURCE_DUMP"]
if test_database != "hongyijig_sseries_test_9c7f17f":
    raise RuntimeError("Unsafe disposable database name")
subprocess.run(["dropdb", *connection, "--if-exists", test_database], env=environment, check=True)
subprocess.run(
    ["pg_dump", *connection, "-Fc", "-f", source_dump, "HongyijigTech_10Feb"],
    env=environment,
    check=True,
)
subprocess.run(["createdb", *connection, test_database], env=environment, check=True)
subprocess.run(
    ["pg_restore", *connection, "--no-owner", "-d", test_database, source_dump],
    env=environment,
    check=True,
)
subprocess.run(
    [
        "psql", *connection, "-d", test_database, "-v", "ON_ERROR_STOP=1", "-c",
        "UPDATE ir_cron SET active=false; "
        "UPDATE fetchmail_server SET active=false; "
        "UPDATE ir_mail_server SET active=false;",
    ],
    env=environment,
    check=True,
)
PY

export HJIG_ISOLATED_TEST_DB="${test_database}"
"${odoo_python}" "${odoo_bin}" \
    -c "${odoo_config}" \
    -d "${test_database}" \
    --db-filter="^${test_database}$" \
    --addons-path="${addons_path}" \
    --http-interface=127.0.0.1 \
    --http-port=18085 \
    --gevent-port=18086 \
    --workers=0 \
    --max-cron-threads=0 \
    --stop-after-init \
    -u new_hongyijig_custom \
    --test-enable \
    --test-tags=/new_hongyijig_custom \
    --log-level=test \
    --logfile="${test_log}"

grep -q "0 failed, 0 error(s)" "${test_log}"
grep -Eq "[0-9]+ tests" "${test_log}"

"${odoo_python}" "${odoo_bin}" shell \
    -c "${odoo_config}" \
    -d "${test_database}" \
    --no-http \
    --addons-path="${addons_path}" \
    > "${validation_log}" 2>&1 <<'PY'
required_models = {
    "hjig.sseries.intake.submission",
    "hjig.sseries.intake.project",
    "hjig.sseries.intake.component",
    "hjig.sseries.case",
    "hjig.programme.run",
    "hjig.portfolio.guard",
    "hjig.sourcebridge.engagement",
}
missing = sorted(name for name in required_models if name not in env)
if missing:
    raise RuntimeError(f"Missing governed models: {missing}")
module = env["ir.module.module"].search([("name", "=", "new_hongyijig_custom")], limit=1)
if module.installed_version != "19.0.3.10.0":
    raise RuntimeError(f"Unexpected installed version: {module.installed_version}")
if env["hjig.sseries.case"].search_count([]):
    raise RuntimeError("Clone validation found unexpected pre-existing S-Series cases")
if not env.ref("new_hongyijig_custom.group_hjig_sseries_user", raise_if_not_found=False):
    raise RuntimeError("S-Series user group is missing")
if not env.ref("new_hongyijig_custom.group_hjig_sseries_manager", raise_if_not_found=False):
    raise RuntimeError("S-Series manager group is missing")
print("SSERIES_FOUNDATION_PASS version=19.0.3.10.0 cases=0 production_untouched=true")
env.cr.rollback()
PY

grep -q "SSERIES_FOUNDATION_PASS" "${validation_log}"
test "$(systemctl is-active odoo.service)" = "active"
test "$(systemctl is-active odoo-production.service)" = "active"
test_count="$(sed -n 's/.*Ran \([0-9][0-9]*\) tests.*/\1/p' "${test_log}" | tail -1)"
echo "HJIG_CLONE_TEST_PASS release=${release_code} tests=${test_count:-unknown} failures=0 errors=0 production_untouched=true"
