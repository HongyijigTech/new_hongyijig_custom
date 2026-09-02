"""Terminate only idle PostgreSQL backends for one disposable S-Series clone."""

import re
import subprocess


DATABASE = "hongyijig_sseries_test_0dc3835"
BACKEND_RE = re.compile(
    rf"^postgres: 16/main: hongyijig {re.escape(DATABASE)} .* "
    r"idle(?: in transaction)?$"
)


def exact_idle_backends():
    output = subprocess.run(
        ["/bin/ps", "-eo", "pid=,args="],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    result = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_text, command = stripped.split(maxsplit=1)
        if BACKEND_RE.fullmatch(command):
            result.append((int(pid_text), command))
    return result


candidates = exact_idle_backends()
if not candidates:
    print(f"EXACT_DISPOSABLE_BACKEND_CLEANUP database={DATABASE} candidates=0")
    raise SystemExit(0)

current = dict(exact_idle_backends())
for pid, expected_command in candidates:
    if current.get(pid) != expected_command:
        raise RuntimeError(f"Backend changed before cleanup: {pid}")

subprocess.run(
    ["sudo", "-n", "/bin/kill", "-TERM", *[str(pid) for pid, _ in candidates]],
    check=True,
)
print(
    f"EXACT_DISPOSABLE_BACKEND_CLEANUP database={DATABASE} "
    f"terminated={len(candidates)} other_databases_untouched=true"
)
