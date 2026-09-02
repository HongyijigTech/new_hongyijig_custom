"""Delete only explicitly approved disposable S-Series clone databases."""

import configparser
import os
import re
import subprocess

import psycopg2


SAFE_DATABASE = re.compile(r"^hongyijig_sseries_test_[0-9a-f]{7}$")

config = configparser.ConfigParser()
config.read("/etc/odoo.conf")
options = config["options"]
connection = psycopg2.connect(
    host=options.get("db_host", "localhost"),
    port=options.get("db_port", "5432"),
    user=options.get("db_user", "hongyijig"),
    password=options.get("db_password", ""),
    dbname="postgres",
)
connection.autocommit = True
try:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT datname FROM pg_database "
            "WHERE datname LIKE 'hongyijig_sseries_test_%%' ORDER BY datname"
        )
        databases = [row[0] for row in cursor.fetchall()]
        unsafe = [name for name in databases if not SAFE_DATABASE.fullmatch(name)]
        if unsafe:
            raise RuntimeError("Refusing cleanup because unexpected database names exist: %r" % unsafe)
finally:
    connection.close()

environment = os.environ.copy()
environment["PGPASSWORD"] = options.get("db_password", "")
connection_args = [
    "-h", options.get("db_host", "localhost"),
    "-p", options.get("db_port", "5432"),
    "-U", options.get("db_user", "hongyijig"),
]
for database in databases:
    subprocess.run(
        ["dropdb", *connection_args, "--force", database],
        env=environment,
        check=True,
    )
    print("DROPPED_DISPOSABLE_DATABASE=" + database, flush=True)

print(
    "SSERIES_DISPOSABLE_DATABASE_CLEANUP_PASS count=%s production=untouched"
    % len(databases)
)
