#!/usr/bin/env bash
set -euo pipefail

ssh -tt \
  -i /Users/jagdeepkhattar/.ssh/hjig_sseries_staging \
  -o IdentitiesOnly=yes \
  hongyi-jig-erp@10.10.71.37 \
  'set -eu
   targets=""
   /bin/ps -eo pid=,args= | while read -r pid args; do
     case "${args}" in
       "postgres: 16/main: hongyijig hongyijig_sseries_test_"*" idle")
         printf "%s\n" "${pid}"
         ;;
     esac
   done > /tmp/hjig_sseries_idle_backend_pids.txt
   while read -r pid; do
     test -n "${pid}" || continue
     args=$(/bin/ps -p "${pid}" -o args=)
     case "${args}" in
       "postgres: 16/main: hongyijig hongyijig_sseries_test_"*" idle") ;;
       *) echo "Refusing cleanup: PID ${pid} no longer matches exact disposable idle backend"; exit 1 ;;
     esac
     targets="${targets} ${pid}"
   done < /tmp/hjig_sseries_idle_backend_pids.txt
   if test -z "${targets}"; then
     echo "No exact disposable idle S-Series backend matched."
   else
     sudo /bin/kill -TERM ${targets}
     echo "Terminated exact disposable idle S-Series backends:${targets}"
   fi
   /usr/bin/systemctl is-active odoo.service
   /usr/bin/systemctl is-active odoo-production.service
   echo "OS_SCOPED_SSERIES_BACKEND_CLEANUP_PASS production=untouched"'

echo "Return to Codex and type done."
read -r -p "Press Enter to close this window."
