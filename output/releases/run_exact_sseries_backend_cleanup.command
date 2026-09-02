#!/usr/bin/env bash
set -euo pipefail

ssh -tt \
  -i /Users/jagdeepkhattar/.ssh/hjig_sseries_staging \
  -o IdentitiesOnly=yes \
  hongyi-jig-erp@10.10.71.37 \
  'set -eu
   targets="1012413 1012422 1012428 1012432 1012440 1012446 1012449 1012459 1012469 1012472 1012478 1012486 1012496 1012506 1012509 1012516 1012519 1012611"
   for pid in ${targets}; do
     args=$(/bin/ps -p "${pid}" -o args=)
     case "${args}" in
       "postgres: 16/main: hongyijig hongyijig_sseries_test_"*" idle") ;;
       *) echo "Refusing cleanup: PID ${pid} is not a disposable idle S-Series backend"; exit 1 ;;
     esac
   done
   sudo /bin/kill -TERM ${targets}
   echo "Exact disposable S-Series database backends terminated; production untouched."'

echo "Scoped S-Series backend cleanup finished. Return to Codex and type done."
read -r -p "Press Enter to close this window."
