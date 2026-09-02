reference = "PB-N8NSMOKE-20260831A"
Submission = env["hjig.sseries.intake.submission"].sudo()
Gateway = env["hjig.sseries.intake.attachment.gateway"].sudo()

submissions = Submission.search([("client_submission_id", "=", reference)])
if len(submissions) != 1:
    raise RuntimeError(f"Expected one immutable submission, got {len(submissions)}")
submission = submissions
if len(submission.project_ids) != 1:
    raise RuntimeError(f"Expected one intake project, got {len(submission.project_ids)}")
project = submission.project_ids
if len(project.component_ids) != 1:
    raise RuntimeError(f"Expected one component, got {len(project.component_ids)}")
component = project.component_ids
if len(project.case_id) != 1 or not project.case_id.lead_id:
    raise RuntimeError("Published n8n intake did not create one CRM-spine case/opportunity")
if len(submission.case_ids.mapped("lead_id")) != 1:
    raise RuntimeError("Website submission maps to more or less than one CRM opportunity")
gateway = Gateway.search([("client_submission_id", "=", reference)])
if len(gateway) != 1:
    raise RuntimeError(f"Expected one governed attachment gateway, got {len(gateway)}")
if gateway.component_id != component:
    raise RuntimeError("Clean attachment was not claimed by the exact intake component")
if component.reference_image_attachment_id != gateway.attachment_id:
    raise RuntimeError("Component and gateway attachment authority differ")
if gateway.upload_status != "scanned_clean_private" or gateway.scan_result != "clean":
    raise RuntimeError("Claimed attachment lacks clean malware-scan authority")
if gateway.attachment_id.access_token:
    raise RuntimeError("Claimed attachment unexpectedly has a public token")

print(
    "HJIG_PUBLISHED_N8N_FULL_INTAKE_PASS "
    f"submission={reference} projects=1 components=1 cases=1 "
    f"crm_opportunities=1 attachment={gateway.name} "
    "scan_clean=true private=true tokenless=true production_untouched=true"
)
env.cr.rollback()
