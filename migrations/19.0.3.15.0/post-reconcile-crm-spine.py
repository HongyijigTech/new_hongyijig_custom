"""Reconcile existing opportunities onto the governed accountability spine."""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["hjig.sseries.intake.submission"].search([])._ensure_crm_spine()
    Lead = env["crm.lead"]
    for lead in Lead.search([("active", "=", True), ("type", "=", "opportunity")]):
        stage_key = Lead._hjig_stage_key_from_id(lead.stage_id.id)
        if stage_key in ("pre_fd", "fd"):
            lead._hjig_route_accountability("pre_fd_fd")
        elif stage_key in ("p", "s", "order_punch", "b_handover"):
            lead._hjig_route_accountability("p_s")
