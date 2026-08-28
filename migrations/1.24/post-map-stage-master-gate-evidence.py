"""Map every authoritative checklist item to named or stage-master evidence."""


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    versions = env["hjig.programme.template.version"].search([
        ("state", "in", ["draft", "review"]),
        ("execution_mode", "=", "governed_gates"),
    ])
    versions._sync_authoritative_gate_checklists()
