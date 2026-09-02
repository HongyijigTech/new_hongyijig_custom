"""Odoo shell payload: provision approved staging CRM accountability identities."""

Users = env["res.users"].sudo().with_context(no_reset_password=True)
intake_email = "intake@thehongyijig.com"
business_email = "businesscrm@thehongyijig.com"

intake = Users.search([("login", "=", "soniakhattar")], limit=1)
if not intake or not intake.active or intake.share:
    raise RuntimeError("The existing staging Intake internal user is unavailable")
intake.write({"email": intake_email})

business = Users.search([
    "|",
    ("login", "=ilike", business_email),
    ("partner_id.email", "=ilike", business_email),
], limit=1)
required_groups = (
    env.ref("sales_team.group_sale_salesman_all_leads")
    | env.ref("new_hongyijig_custom.group_hjig_sseries_manager")
)
if not business:
    business = Users.create({
        "name": "Business CRM Team",
        "login": business_email,
        "email": business_email,
        "company_id": env.company.id,
        "company_ids": [(6, 0, [env.company.id])],
        "group_ids": [(6, 0, required_groups.ids)],
        "active": True,
    })
else:
    business.write({
        "name": "Business CRM Team",
        "login": business_email,
        "email": business_email,
        "group_ids": [(4, group_id) for group_id in required_groups.ids],
        "active": True,
    })

parameters = env["ir.config_parameter"].sudo()
parameters.set_param("hjig.crm.pre_fd_fd_owner_email", intake_email)
parameters.set_param("hjig.crm.p_s_owner_email", business_email)

Lead = env["crm.lead"].sudo()
for lead in Lead.search([("active", "=", True), ("type", "=", "opportunity")]):
    stage_key = Lead._hjig_stage_key_from_id(lead.stage_id.id)
    if stage_key in ("pre_fd", "fd"):
        lead._hjig_route_accountability("pre_fd_fd")
    elif stage_key in ("p", "s", "order_punch", "b_handover"):
        lead._hjig_route_accountability("p_s")

env.cr.commit()

if intake.partner_id.email.lower() != intake_email:
    raise RuntimeError("Intake email mapping verification failed")
if not business.has_group("new_hongyijig_custom.group_hjig_sseries_manager"):
    raise RuntimeError("Business CRM S-Series Manager role verification failed")
if not business.has_group("sales_team.group_sale_salesman_all_leads"):
    raise RuntimeError("Business CRM all-opportunity role verification failed")
missing = Lead.search_count([
    ("active", "=", True),
    ("type", "=", "opportunity"),
    ("hjig_owner_routing_state", "=", "missing"),
])
if missing:
    raise RuntimeError("CRM owner routing still has %s unresolved opportunities" % missing)

print(
    "STAGING_CRM_ACCOUNTABILITY_PASS "
    "pre_fd_fd=%s p_s=%s unresolved=0 invitation_sent=false password_set=false "
    "production=untouched"
    % (intake_email, business_email)
)
