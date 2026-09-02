"""Verify clean-file acceptance and inert EICAR signature rejection by clamdscan."""

import base64
import os
import subprocess
import tempfile


SCANNER = "/usr/bin/clamdscan"
EICAR_BASE64 = (
    "WDVPIVAlQEFQWzRcUFpYNTQoUF4pN0NDKTd9JEVJQ0FSLVNUQU5EQVJELUFOVElW"
    "SVJVUy1URVNULUZJTEUhJEgrSCo="
)


def scan(payload):
    path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix="hjig-clamav-verification-", delete=False
        ) as handle:
            path = handle.name
            os.chmod(path, 0o600)
            handle.write(payload)
        return subprocess.run(
            [SCANNER, "--fdpass", "--no-summary", path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=False,
            text=True,
        )
    finally:
        if path:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass


clean = scan(b"Hongyi S-Series clean attachment verification\n")
if clean.returncode != 0 or " OK" not in clean.stdout:
    raise RuntimeError(f"Clean-file scan failed: rc={clean.returncode} {clean.stdout!r}")

eicar = scan(base64.b64decode(EICAR_BASE64))
if eicar.returncode != 1 or "FOUND" not in eicar.stdout:
    raise RuntimeError(f"EICAR rejection failed: rc={eicar.returncode} {eicar.stdout!r}")

print(
    "HJIG_CLAMAV_BEHAVIOUR_PASS clean=accepted eicar=rejected "
    "temporary_quarantine_removed=true"
)
