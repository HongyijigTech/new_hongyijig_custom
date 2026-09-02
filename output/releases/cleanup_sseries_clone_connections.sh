#!/usr/bin/env bash
set -euo pipefail

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
    "-d", "postgres",
]
sql = """
WITH targets AS (
    SELECT pid
    FROM pg_stat_activity
    WHERE usename = current_user
      AND datname LIKE 'hongyijig_sseries_test_%'
      AND state = 'idle'
      AND pid <> pg_backend_pid()
)
SELECT count(*) FROM targets WHERE pg_terminate_backend(pid);
"""
result = subprocess.run(
    ["psql", *connection, "-At", "-v", "ON_ERROR_STOP=1", "-c", sql],
    env=environment,
    check=True,
    capture_output=True,
    text=True,
)
print("SSERIES_IDLE_CONNECTIONS_TERMINATED=" + result.stdout.strip())
PY

restart_staging
staging_stopped=0
trap - EXIT
test "$(systemctl is-active odoo-production.service)" = "active"
echo "SSERIES_CONNECTION_CLEANUP_PASS staging=active production=untouched"
