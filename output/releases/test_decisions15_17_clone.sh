#!/usr/bin/env bash
# Disposable clone test only. Never upgrades the live staging database or service.
set -euo pipefail

package_path="$1"
expected_sha="$2"
run_token="d1517_$(date -u +%Y%m%d%H%M%S)_$$"
test_database="hongyijig_sseries_test_${run_token}"
work_root="/home/hongyi-jig-erp/releases/work/${run_token}"
candidate_root="${work_root}/candidate"
source_dump="${work_root}/staging_source.dump"
test_log="${work_root}/odoo_tests.log"
odoo_python="/home/hongyi-jig-erp/odoo/venv19/bin/python3"
odoo_bin="/home/hongyi-jig-erp/odoo/odoo-bin"
odoo_config="/etc/odoo.conf"
addons_path="${candidate_root},/home/hongyi-jig-erp/odoo/staging_overrides,/home/hongyi-jig-erp/odoo/odoo/addons,/home/hongyi-jig-erp/odoo/addons,/home/hongyi-jig-erp/odoo/enterprise,/home/hongyi-jig-erp/odoo/hongyijigTech_custom"

cleanup() {
    status=$?
    trap - EXIT INT TERM HUP
    HJIG_TEST_DATABASE="${test_database}" "${odoo_python}" - <<'PY'
import configparser
import os
import subprocess

name = os.environ["HJIG_TEST_DATABASE"]
if not name.startswith("hongyijig_sseries_test_d1517_"):
    raise RuntimeError("Refusing cleanup outside the Decision 15-17 disposable namespace")
config = configparser.ConfigParser()
config.read("/etc/odoo.conf")
options = config["options"]
environment = os.environ.copy()
environment["PGPASSWORD"] = options.get("db_password", "")
connection = ["-h", options.get("db_host", "localhost"), "-p", options.get("db_port", "5432"), "-U", options.get("db_user", "hongyijig")]
subprocess.run(["dropdb", *connection, "--if-exists", name], env=environment, check=True)
PY
    printf 'DISPOSABLE_DB_CLEANUP_COMPLETE name=%s exit_status=%s\n' "${test_database}" "${status}"
    exit "${status}"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

test "$(systemctl is-active odoo.service)" = "active"
test "$(systemctl is-active odoo-production.service)" = "active"
test -f "${package_path}"
printf '%s  %s\n' "${expected_sha}" "${package_path}" | sha256sum --check --status

mkdir -p "${candidate_root}"
tar -xzf "${package_path}" -C "${candidate_root}"
grep -q "'version': '19.0.3.32.0'" "${candidate_root}/new_hongyijig_custom/__manifest__.py"

export HJIG_TEST_DATABASE="${test_database}"
export HJIG_SOURCE_DUMP="${source_dump}"
"${odoo_python}" - <<'PY'
import configparser
import os
import subprocess

name = os.environ["HJIG_TEST_DATABASE"]
if not name.startswith("hongyijig_sseries_test_d1517_"):
    raise RuntimeError("Unsafe disposable test database name")
config = configparser.ConfigParser()
config.read("/etc/odoo.conf")
options = config["options"]
environment = os.environ.copy()
environment["PGPASSWORD"] = options.get("db_password", "")
connection = ["-h", options.get("db_host", "localhost"), "-p", options.get("db_port", "5432"), "-U", options.get("db_user", "hongyijig")]

# The live staging database appears only as the pg_dump source.  No live write occurs.
subprocess.run(["pg_dump", *connection, "-Fc", "-f", os.environ["HJIG_SOURCE_DUMP"], "HongyijigTech_10Feb"], env=environment, check=True)
subprocess.run(["createdb", *connection, name], env=environment, check=True)
subprocess.run(["pg_restore", *connection, "--no-owner", "-d", name, os.environ["HJIG_SOURCE_DUMP"]], env=environment, check=True)
subprocess.run([
    "psql", *connection, "-d", name, "-v", "ON_ERROR_STOP=1", "-c",
    "UPDATE ir_cron SET active=false; UPDATE fetchmail_server SET active=false; UPDATE ir_mail_server SET active=false; "
    "UPDATE ir_config_parameter SET value='0' WHERE key='new_hongyijig_custom.staging_single_internal_user_guard';",
], env=environment, check=True)
PY

printf 'CLONE_TEST_START db=%s\n' "${test_database}"
"${odoo_python}" "${odoo_bin}" \
    -c "${odoo_config}" \
    -d "${test_database}" \
    --db-filter="^${test_database}$" \
    --addons-path="${addons_path}" \
    --http-interface=127.0.0.1 \
    --http-port=18157 \
    --gevent-port=18158 \
    --workers=0 \
    --max-cron-threads=0 \
    --stop-after-init \
    -u new_hongyijig_custom \
    --test-enable \
    --test-tags=/new_hongyijig_custom \
    --log-level=test \
    --logfile="${test_log}"

cat "${test_log}"
grep -q "0 failed, 0 error(s)" "${test_log}"
printf 'CLONE_TEST_PASS db=%s\n' "${test_database}"
