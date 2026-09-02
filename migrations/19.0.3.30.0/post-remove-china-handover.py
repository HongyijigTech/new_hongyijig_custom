"""Retire legacy China Handover authority without breaking historical artifacts."""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    # Existing hjig.sseries.artifact.template_id records use ondelete="restrict".
    # Keep that historic provenance intact and prevent any future requirement
    # creation by retiring the legacy template from active authority.
    env["hjig.sseries.document.template"].with_context(install_mode=True).search([
        ("code", "=", "S6-CHINA-HANDOVER"),
    ]).write({"active": False})
