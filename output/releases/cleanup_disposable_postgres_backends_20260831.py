"""Fail-closed cleanup of idle PostgreSQL backends for disposable UAT/test DBs."""

import argparse
import re
import subprocess


LIVE_DATABASES = {
    "HongyijigTech_10Feb",
    "hongyijig_30April_db",
    "postgres",
    "template0",
    "template1",
}
SAFE_DATABASE_PATTERNS = (
    re.compile(r"^HongyiWA_Prod_[A-Za-z0-9_]+_test$"),
    re.compile(r"^HongyijigTech_[A-Za-z0-9_]*(?:test|diag|uat)[A-Za-z0-9_]*$", re.I),
    re.compile(r"^hjig_uat_[A-Za-z0-9_]+$", re.I),
    re.compile(r"^hongyijig_(?:bseries|sseries)_[A-Za-z0-9_]+$", re.I),
    re.compile(r"^hongyijig_[A-Za-z0-9_]*_diag[A-Za-z0-9_]*$", re.I),
)
BACKEND_RE = re.compile(
    r"^postgres: 16/main: hongyijig (?P<database>\S+) .* (?P<state>idle(?: in transaction)?)$"
)


def process_rows():
    output = subprocess.run(
        ["/bin/ps", "-eo", "pid=,args="],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    ).stdout
    rows = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_text, args = stripped.split(maxsplit=1)
        match = BACKEND_RE.fullmatch(args)
        if not match:
            continue
        database = match.group("database")
        if database in LIVE_DATABASES:
            continue
        if any(pattern.fullmatch(database) for pattern in SAFE_DATABASE_PATTERNS):
            rows.append((int(pid_text), database, args))
    return rows


parser = argparse.ArgumentParser()
parser.add_argument("--execute", action="store_true")
args = parser.parse_args()
candidates = process_rows()
if not candidates:
    print("HJIG_DISPOSABLE_BACKEND_CLEANUP no_candidates=true live_databases_untouched=true")
    raise SystemExit(0)

for pid, database, _command in candidates:
    print(f"CANDIDATE pid={pid} database={database} state=idle")

if not args.execute:
    print(
        f"HJIG_DISPOSABLE_BACKEND_AUDIT candidates={len(candidates)} "
        "execution=false live_databases_untouched=true"
    )
    raise SystemExit(0)

current = {pid: command for pid, _database, command in process_rows()}
for pid, database, expected_command in candidates:
    if current.get(pid) != expected_command:
        raise RuntimeError(f"PID changed before cleanup: {pid} ({database})")

subprocess.run(
    ["sudo", "/bin/kill", "-TERM", *[str(pid) for pid, _database, _command in candidates]],
    check=True,
)
print(
    f"HJIG_DISPOSABLE_BACKEND_CLEANUP terminated={len(candidates)} "
    "live_databases_untouched=true production_untouched=true"
)
