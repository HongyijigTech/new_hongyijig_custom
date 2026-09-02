"""Reproduce the guarded active-module source hash used by staging deploy scripts."""

import hashlib
from pathlib import Path


ROOT = Path("/home/hongyi-jig-erp/odoo/staging_overrides/new_hongyijig_custom")
if not ROOT.is_dir():
    raise RuntimeError(f"Active staging module is missing: {ROOT}")

lines = []
for path in sorted(ROOT.rglob("*")):
    if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
        continue
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    lines.append(f"{digest}  {path}\n")

tree_digest = hashlib.sha256("".join(lines).encode()).hexdigest()
print(f"HJIG_ACTIVE_MODULE_SHA256 version_file={ROOT / '__manifest__.py'} sha256={tree_digest}")
