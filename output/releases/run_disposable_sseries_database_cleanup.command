#!/usr/bin/env bash
set -euo pipefail

ssh -tt \
  -i /Users/jagdeepkhattar/.ssh/hjig_sseries_staging \
  -o IdentitiesOnly=yes \
  hongyi-jig-erp@10.10.71.37 \
  'set -eu
   targets="1018127 1018132 1018137 1018142 1018145 1018149 1018151 1018155 1018158 1018164 1018169 1018171 1018175 1018178 1018182 1018185 1018188 1018196 1018198 1018201 1018205 1018207 1018211 1018215 1018217 1018220 1018224"
   for pid in ${targets}; do
     args=$(/bin/ps -p "${pid}" -o args=)
     case "${args}" in
       "postgres: 16/main: hongyijig hongyijig_sseries_test_"*" idle") ;;
       *) echo "Refusing cleanup: PID ${pid} is not a disposable idle S-Series backend"; exit 1 ;;
     esac
   done
   sudo /bin/kill -TERM ${targets}
   /home/hongyi-jig-erp/odoo/venv19/bin/python3 /home/hongyi-jig-erp/releases/incoming/drop_disposable_sseries_test_databases.py'

echo "Disposable S-Series database cleanup finished. Return to Codex and type done."
read -r -p "Press Enter to close this window."
