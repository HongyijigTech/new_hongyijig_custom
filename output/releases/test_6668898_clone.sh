#!/usr/bin/env bash
set -euo pipefail

release_code="6668898"
package_path="/home/hongyi-jig-erp/releases/incoming/Hongyi_Odoo_SSeries_6668898.tar.gz"
expected_sha="ca119bd1579264b506ddaef2d12c2ad18fea72923f3c56d2ec8b21712fc3b004"
work_root="/home/hongyi-jig-erp/releases/work/${release_code}"
candidate_root="${work_root}/candidate"
source_dump="${work_root}/HongyijigTech_10Feb_source.dump"
test_database="hongyijig_sseries_test_6668898"
test_log="${work_root}/post_install_tests.log"
validation_log="${work_root}/sseries_validation.log"
render_qa_root="${work_root}/rendered-qa"
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
if test_database != "hongyijig_sseries_test_6668898":
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
grep -q "'version': '19.0.3.26.0'" "${candidate_root}/new_hongyijig_custom/__manifest__.py"
printf '%s  %s\n' \
    "cdccee7ebe36c160e44a03b38281ead11f180c02284affab9b1bfc2ea1e093a9" \
    "${candidate_root}/new_hongyijig_custom/resources/sseries_internal_uat/s4_nda_r1/Hongyi_S4_NDA_Reusable_Odoo_Master_R1_INTERNAL_UAT.docx" \
    | sha256sum --check --status
printf '%s  %s\n' \
    "0fb55ea38478875e610b5d76ae152f27a09782b331abfbbf685d8bbcf36ddd38" \
    "${candidate_root}/new_hongyijig_custom/resources/sseries_internal_uat/s4_nda_r1/Hongyi_S4_NDA_Reusable_Odoo_Master_R1_INTERNAL_UAT.pdf" \
    | sha256sum --check --status
printf '%s  %s\n' \
    "70a4fb1d5df611cacc3992eb88a4745ddda032cb244d9c575396371c6b390592" \
    "${candidate_root}/new_hongyijig_custom/resources/sseries_internal_uat/s4_nda_r1/Hongyi_S4_NDA_Reusable_Odoo_Master_R1_Evidence_2026-08-31.json" \
    | sha256sum --check --status
printf '%s  %s\n' \
    "213e2b3fa7a050b7871445263cf7d828c0416339093f061ec3fffbe4d14cabaf" \
    "${candidate_root}/new_hongyijig_custom/resources/sseries_internal_uat/activation_handover_r1/Hongyi_S4_Acceptance_Record_EXACT_NATIVE_TEMPLATE_R1_SANITIZED.docx" \
    | sha256sum --check --status
printf '%s  %s\n' \
    "6a97d8d9607409645f72496e66219aaea0e5f5063994975b1e83f43360751a78" \
    "${candidate_root}/new_hongyijig_custom/resources/sseries_internal_uat/activation_handover_r1/Hongyi_S5_Order_Punch_EXACT_NATIVE_TEMPLATE_R1_SANITIZED.docx" \
    | sha256sum --check --status
printf '%s  %s\n' \
    "5f024369c2e8169fa3690d3dcfaca3e66ae9e6052e9efe6fe2a051d6d4daf06e" \
    "${candidate_root}/new_hongyijig_custom/resources/sseries_internal_uat/activation_handover_r1/Hongyi_S6_Team_Handover_EXACT_NATIVE_TEMPLATE_R1_SANITIZED.docx" \
    | sha256sum --check --status

export HJIG_SOURCE_DUMP="${source_dump}"
export HJIG_TEST_DATABASE="${test_database}"
export HJIG_RENDER_QA_ROOT="${render_qa_root}"
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
if test_database != "hongyijig_sseries_test_6668898":
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
    --http-port=18087 \
    --gevent-port=18088 \
    --workers=0 \
    --max-cron-threads=0 \
    --stop-after-init \
    -u new_hongyijig_custom \
    --test-enable \
    --test-tags=/new_hongyijig_custom \
    --log-level=test \
    --logfile="${test_log}"

grep -q "0 failed, 0 error(s)" "${test_log}"

"${odoo_python}" "${odoo_bin}" shell \
    -c "${odoo_config}" \
    -d "${test_database}" \
    --no-http \
    --addons-path="${addons_path}" \
> "${validation_log}" 2>&1 <<'PY'
import os
from pathlib import Path

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
if module.installed_version != "19.0.3.26.0":
    raise RuntimeError(f"Unexpected installed version: {module.installed_version}")
cases = env["hjig.sseries.case"].search([])
for field_name in (
    "nda_reference", "nda_effective_date", "nda_customer_signed", "nda_hongyi_signed",
):
    if field_name not in env["hjig.sseries.case"]._fields:
        raise RuntimeError(f"Missing S4 NDA evidence field: {field_name}")
if cases.filtered(lambda item: not item.lead_id):
    raise RuntimeError("CRM spine reconciliation left an S-Series case without an opportunity")
for submission in cases.mapped("submission_id"):
    if len(submission.case_ids.mapped("lead_id")) != 1:
        raise RuntimeError("One website submission must map to exactly one CRM opportunity")

Template = env["hjig.sseries.document.template"]
if Template.search_count([]) != 24:
    raise RuntimeError("Unexpected controlled S-Series document-template count")
nda = Template.search([("code", "=", "S4-NDA")], limit=1)
if nda.master_file_id != "LOCAL-S4-NDA-REUSABLE-ODOO-MASTER-R1":
    raise RuntimeError("S4 NDA reusable master id mismatch")
if nda.source_sha256 != "cdccee7ebe36c160e44a03b38281ead11f180c02284affab9b1bfc2ea1e093a9":
    raise RuntimeError("S4 NDA reusable master digest mismatch")
if nda.expected_page_count != 4:
    raise RuntimeError("S4 NDA controlled page count mismatch")
if nda.authority_status != "REUSABLE_INTERNAL_UAT_USER_AND_LEGAL_APPROVAL_PENDING":
    raise RuntimeError("S4 NDA authority status mismatch")
if nda.rendering_status != "blocked" or nda.approved_for_internal_uat_generation:
    raise RuntimeError("S4 NDA must remain fail-closed")
if nda.user_final_approval or nda.customer_issue_allowed:
    raise RuntimeError("S4 NDA must not be externally issuable")
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
expected_approved = {"S4-ACCEPTANCE", "S5-ORDER-PUNCH", "S5-PROFORMA", "S6-TEAM-HANDOVER"}
if set(approved.mapped("code")) != expected_approved:
    raise RuntimeError("Unexpected internal-UAT generation authority set")
if activation.filtered("user_final_approval"):
    raise RuntimeError("Pending authority records must not have user final approval")
if activation.filtered("customer_issue_allowed") or activation.filtered("supplier_issue_allowed"):
    raise RuntimeError("Pending activation records must remain fail-closed for external issue")
pending = activation - approved
if pending.filtered("template_visual_qa_verified") or pending.filtered("template_content_qa_verified"):
    raise RuntimeError("Pending candidate templates must not be represented as QA-verified")
if approved.filtered("template_visual_qa_verified") or approved.filtered("template_content_qa_verified"):
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
reference_case = env["hjig.sseries.case"].search([("name", "=", "S/2026/000003")], limit=1)
if not reference_case:
    raise RuntimeError("Reference S-Series render case is unavailable")
render_root = Path(os.environ["HJIG_RENDER_QA_ROOT"])
render_root.mkdir(parents=True, exist_ok=True)
for code in ("S4-ACCEPTANCE", "S5-ORDER-PUNCH", "S6-TEAM-HANDOVER"):
    artifact = reference_case.artifact_ids.filtered(lambda item: item.code == code)[:1]
    if not artifact:
        raise RuntimeError(f"Reference artifact missing for {code}")
    pdf_bytes, manifest = artifact._render_exact_native_pdf()
    if manifest["unresolved_placeholder_count"] != 0:
        raise RuntimeError(f"Unresolved renderer placeholders for {code}")
    (render_root / f"{code}_INTERNAL_UAT.pdf").write_bytes(pdf_bytes)
print(
    "SSERIES_AUTHORITY_PASS version=19.0.3.26.0 templates=24 activation_records=13 "
    f"cases={len(cases)} one_crm_spine=true "
    "core_internal_uat_renderers=4 bseries_preserved=true production_untouched=true"
)
env.cr.rollback()
PY

grep -q "SSERIES_AUTHORITY_PASS" "${validation_log}"
test "$(systemctl is-active odoo.service)" = "active"
test "$(systemctl is-active odoo-production.service)" = "active"
test_count="$(grep -Eo '0 failed, 0 error\(s\) of [0-9]+ tests' "${test_log}" | tail -1 | grep -Eo '[0-9]+ tests' | awk '{print $1}')"
echo "HJIG_CLONE_TEST_PASS release=${release_code} tests=${test_count:-unknown} failures=0 errors=0 production_untouched=true"
