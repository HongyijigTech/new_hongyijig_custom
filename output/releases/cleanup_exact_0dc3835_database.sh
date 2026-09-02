#!/usr/bin/env bash
set -euo pipefail

database="hongyijig_sseries_test_0dc3835"
odoo_python="/home/hongyi-jig-erp/odoo/venv19/bin/python3"
staging_stopped=0

restart_staging() {
    if test "${staging_stopped}" -eq 1; then
        sudo -n /usr/bin/systemctl start odoo.service
        test "$(systemctl is-active odoo.service)" = "active"
    fi
}
trap restart_staging EXIT

test "$(systemctl is-active odoo.service)" = "active"
test "$(systemctl is-active odoo-production.service)" = "active"
sudo -n /usr/bin/systemctl stop odoo.service
staging_stopped=1
test "$(systemctl is-active odoo-production.service)" = "active"

HJIG_EXACT_TEST_DATABASE="${database}" "${odoo_python}" - <<'PY'
import configparser
import os
import subprocess

database = os.environ["HJIG_EXACT_TEST_DATABASE"]
if database != "hongyijig_sseries_test_0dc3835":
    raise RuntimeError("Unsafe disposable database name")
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
subprocess.run(
    [
        "psql", *connection, "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-c",
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        f"WHERE datname = '{database}' AND pid <> pg_backend_pid();",
    ],
    env=environment,
    check=True,
)
subprocess.run(["dropdb", *connection, "--if-exists", database], env=environment, check=True)
print(f"EXACT_DISPOSABLE_DATABASE_CLEANUP_PASS database={database}")
PY

restart_staging
staging_stopped=0
trap - EXIT
test "$(systemctl is-active odoo-production.service)" = "active"
echo "EXACT_DISPOSABLE_DATABASE_WINDOW_CLEARED staging=active production=untouched"
