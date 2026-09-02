#!/usr/bin/env bash
set -euo pipefail

active_module="/home/hongyi-jig-erp/odoo/staging_overrides/new_hongyijig_custom"
find "${active_module}" \
  -type f \
  ! -path '*/__pycache__/*' \
  ! -name '*.pyc' \
  -print0 \
  | sort -z \
  | xargs -0 sha256sum \
  | sha256sum
