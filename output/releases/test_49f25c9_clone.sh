#!/usr/bin/env bash
set -euo pipefail

release_code="49f25c9"
package_path="/home/hongyi-jig-erp/releases/incoming/Hongyi_Odoo_SSeries_49f25c9.tar.gz"
expected_sha="b53183ca5e61feca4f5a1bc79bfc9f09b5b1545f41da763375d256805a643398"
work_root="/home/hongyi-jig-erp/releases/work/${release_code}"
candidate_root="${work_root}/candidate"
source_dump="${work_root}/HongyijigTech_10Feb_source.dump"
test_database="hongyijig_sseries_test_49f25c9"
test_log="${work_root}/post_install_tests.log"
validation_log="${work_root}/sseries_validation.log"
odoo_python="/home/hongyi-jig-erp/odoo/venv19/bin/python3"
odoo_bin="/home/hongyi-jig-erp/odoo/odoo-bin"
odoo_config="/etc/odoo.conf"
addons_path="${candidate_root},/home/hongyi-jig-erp/odoo/staging_overrides,/home/hongyi-jig-erp/odoo/odoo/addons,/home/hongyi-jig-erp/odoo/addons,/home/hongyi-jig-erp/odoo/enterprise,/home/hongyi-jig-erp/odoo/hongyijigTech_custom"

cleanup_test_database() {
    local exit_status=$?
    set +e
    HJIG_TEST_DATABASE="${test_database}" "${odoo_python}" - <<'PY'
import configparser
import os
import subprocess

test_database = os.environ["HJIG_TEST_DATABASE"]
if test_database != "hongyijig_sseries_test_49f25c9":
    raise RuntimeError("Unsafe disposable database name")
config = configparser.ConfigParser()
config.read("/etc/odoo.conf")
options = config["options"]
environment = os.environ.copy()
environment["PGPASSWORD"] = options.get("db_password", "")
connection = [
    "-h", options.get("db_host", "localhost"),
    "-p", options.get("db_port", "5432"),
    "-U", options.get("db_user", "hongyijig"),
]
subprocess.run(["dropdb", *connection, "--if-exists", test_database], env=environment, check=True)
PY
    local cleanup_status=$?
    if (( cleanup_status != 0 )); then
        echo "WARNING: disposable test database cleanup failed: ${test_database}" >&2
    fi
    exit "${exit_status}"
}
trap cleanup_test_database EXIT

test "$(systemctl is-active odoo.service)" = "active"
test "$(systemctl is-active odoo-production.service)" = "active"
test -f "${package_path}"
printf '%s  %s\n' "${expected_sha}" "${package_path}" | sha256sum --check --status

mkdir -p "${work_root}"
if test -e "${candidate_root}"; then
    mv "${candidate_root}" "${work_root}/candidate_previous_$(date +%Y%m%d_%H%M%S)"
fi
mkdir -p "${candidate_root}"
tar -xzf "${package_path}" -C "${candidate_root}"
grep -q "'version': '19.0.3.23.0'" "${candidate_root}/new_hongyijig_custom/__manifest__.py"

export HJIG_SOURCE_DUMP="${source_dump}"
export HJIG_TEST_DATABASE="${test_database}"
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
]
test_database = os.environ["HJIG_TEST_DATABASE"]
source_dump = os.environ["HJIG_SOURCE_DUMP"]
if test_database != "hongyijig_sseries_test_49f25c9":
    raise RuntimeError("Unsafe disposable database name")
subprocess.run(["dropdb", *connection, "--if-exists", test_database], env=environment, check=True)
subprocess.run(
    ["pg_dump", *connection, "-Fc", "-f", source_dump, "HongyijigTech_10Feb"],
    env=environment,
    check=True,
)
subprocess.run(["createdb", *connection, test_database], env=environment, check=True)
subprocess.run(
    ["pg_restore", *connection, "--no-owner", "-d", test_database, source_dump],
    env=environment,
    check=True,
)
subprocess.run(
    [
        "psql", *connection, "-d", test_database, "-v", "ON_ERROR_STOP=1", "-c",
        "UPDATE ir_cron SET active=false; "
        "UPDATE fetchmail_server SET active=false; "
        "UPDATE ir_mail_server SET active=false; "
        "UPDATE ir_config_parameter SET value='0' "
        "WHERE key='new_hongyijig_custom.staging_single_internal_user_guard';",
    ],
    env=environment,
    check=True,
)
PY

"${odoo_python}" "${odoo_bin}" \
    -c "${odoo_config}" \
    -d "${test_database}" \
    --db-filter="^${test_database}$" \
    --addons-path="${addons_path}" \
    --http-interface=127.0.0.1 \
    --http-port=18085 \
    --gevent-port=18086 \
    --workers=0 \
    --max-cron-threads=0 \
    --stop-after-init \
    -u new_hongyijig_custom \
    --test-enable \
    --test-tags=/new_hongyijig_custom \
    --log-level=test \
    --logfile="${test_log}"

grep -q "0 failed, 0 error(s) of 201 tests" "${test_log}"

"${odoo_python}" "${odoo_bin}" shell \
    -c "${odoo_config}" \
    -d "${test_database}" \
    --no-http \
    --addons-path="${addons_path}" \
    > "${validation_log}" 2>&1 <<'PY'
required_models = {
    "hjig.sseries.intake.submission",
    "hjig.sseries.intake.project",
    "hjig.sseries.intake.component",
    "hjig.sseries.intake.gateway",
    "hjig.sseries.intake.attachment.gateway",
    "hjig.mould.change.log",
    "hjig.mould.geometry",
    "hjig.sseries.case",
    "hjig.sseries.document.template",
    "hjig.sseries.artifact",
    "hjig.sseries.b0.handover",
    "hjig.programme.run",
    "hjig.portfolio.guard",
    "hjig.sourcebridge.engagement",
}
missing = sorted(name for name in required_models if name not in env)
if missing:
    raise RuntimeError(f"Missing governed models: {missing}")
module = env["ir.module.module"].search([("name", "=", "new_hongyijig_custom")], limit=1)
if module.installed_version != "19.0.3.23.0":
    raise RuntimeError(f"Unexpected installed version: {module.installed_version}")
cases = env["hjig.sseries.case"].search([])
if cases.filtered(lambda item: not item.lead_id):
    raise RuntimeError("CRM spine reconciliation left an S-Series case without an opportunity")
for submission in cases.mapped("submission_id"):
    if len(submission.case_ids.mapped("lead_id")) != 1:
        raise RuntimeError("One website submission must map to exactly one CRM opportunity")

Template = env["hjig.sseries.document.template"]
if Template.search_count([]) != 24:
    raise RuntimeError("Unexpected controlled S-Series document-template count")
activation_codes = {
    "S4-NDA", "S4-INTRODUCED-PARTY-NOTICE", "S4-DIRECT-ENGAGEMENT-CONSENT",
    "S4-ACCEPTANCE", "S5-ORDER-PUNCH", "S5-PROFORMA", "S5-PAYMENT-EVIDENCE",
    "S5-TAX-INVOICE", "S6-TEAM-HANDOVER", "S6-CHINA-HANDOVER",
    "S6-SUPPLIER-RFQ-EN", "S6-SUPPLIER-RFQ-ZH", "B0-HANDOVER-MANIFEST",
}
activation = Template.search([("code", "in", sorted(activation_codes))])
if set(activation.mapped("code")) != activation_codes:
    raise RuntimeError("Activation authority registry is incomplete")
approved = activation.filtered("approved_for_internal_uat_generation")
if approved.mapped("code") != ["S5-PROFORMA"]:
    raise RuntimeError("Only S5-PROFORMA may have internal-UAT generation authority")
if activation.filtered("user_final_approval"):
    raise RuntimeError("Pending authority records must not have user final approval")
if activation.filtered("customer_issue_allowed") or activation.filtered("supplier_issue_allowed"):
    raise RuntimeError("Pending activation records must remain fail-closed for external issue")
pending = activation - approved
if pending.filtered("template_visual_qa_verified") or pending.filtered("template_content_qa_verified"):
    raise RuntimeError("Pending candidate templates must not be represented as QA-verified")
if approved.template_visual_qa_verified or approved.template_content_qa_verified:
    raise RuntimeError("PI template QA gates must remain separate from internal-UAT authority")
if Template.search([("code", "=", "S5-PAYMENT-EVIDENCE")], limit=1).rendering_status != "blocked":
    raise RuntimeError("Payment evidence must remain blocked without an approved master")
if Template.search([("code", "=", "S5-TAX-INVOICE")], limit=1).rendering_status != "blocked":
    raise RuntimeError("Tax invoice must remain deferred to the Tally boundary")

Artifact = env["hjig.sseries.artifact"]
for method_name in ("action_verify_visual_qa", "action_verify_content_qa", "action_verify_qa"):
    if not hasattr(Artifact, method_name):
        raise RuntimeError(f"Missing governed QA action: {method_name}")

for field_name in (
    "hjig_programme_activation_state",
    "hjig_programme_run_ids",
    "hjig_authorized_user_ids",
):
    if field_name not in env["project.project"]._fields:
        raise RuntimeError(f"Missing preserved project field: {field_name}")
for xmlid in (
    "new_hongyijig_custom.group_hjig_sseries_user",
    "new_hongyijig_custom.group_hjig_sseries_manager",
    "new_hongyijig_custom.menu_hjig_sseries",
    "new_hongyijig_custom.menu_hjig_my_governed_work",
    "new_hongyijig_custom.action_hjig_sseries_cases",
    "new_hongyijig_custom.action_hjig_my_governed_work",
):
    if not env.ref(xmlid, raise_if_not_found=False):
        raise RuntimeError(f"Missing preserved/new UI authority: {xmlid}")
for xmlid in (
    "new_hongyijig_custom.crm_stage_hjig_pre_fd",
    "new_hongyijig_custom.crm_stage_hjig_fd_series",
    "new_hongyijig_custom.crm_stage_hjig_p_series",
    "new_hongyijig_custom.crm_stage_hjig_s_series",
    "new_hongyijig_custom.crm_stage_hjig_order_punch",
    "new_hongyijig_custom.crm_stage_hjig_bseries_handover",
):
    if not env.ref(xmlid, raise_if_not_found=False):
        raise RuntimeError(f"Missing governed CRM spine stage: {xmlid}")
menu = env.ref("new_hongyijig_custom.menu_hjig_sseries")
if menu.group_ids != env.ref("base.group_no_one"):
    raise RuntimeError("Separate S-Series employee menu is not hidden")
print(
    "SSERIES_AUTHORITY_PASS version=19.0.3.23.0 templates=24 activation_records=13 "
    f"cases={len(cases)} only_pi_internal_uat=true one_crm_spine=true "
    "bseries_preserved=true production_untouched=true"
)
env.cr.rollback()
PY

grep -q "SSERIES_AUTHORITY_PASS" "${validation_log}"
test "$(systemctl is-active odoo.service)" = "active"
test "$(systemctl is-active odoo-production.service)" = "active"
echo "HJIG_CLONE_TEST_PASS release=${release_code} tests=201 failures=0 errors=0 production_untouched=true"
