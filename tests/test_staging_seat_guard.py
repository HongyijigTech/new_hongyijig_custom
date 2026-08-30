from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestStagingSeatGuard(TransactionCase):

    def test_guard_blocks_second_active_internal_login(self):
        users = self.env["res.users"].with_context(active_test=False)
        active_internal = users.search([("active", "=", True), ("share", "=", False)])
        keeper = active_internal[:1]
        (active_internal - keeper).write({"active": False})
        self.assertEqual(len(keeper), 1)
        self.env["ir.config_parameter"].sudo().set_param(
            "new_hongyijig_custom.staging_single_internal_user_guard", "1"
        )

        with self.assertRaises(ValidationError):
            users.create({
                "name": "Forbidden Staging Seat",
                "login": "forbidden.staging.seat@test.invalid",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            })

        inactive = users.create({
            "name": "No Login Planned Record",
            "login": "inactive.staging.record@test.invalid",
            "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
        })
        inactive.write({"active": False})
        self.assertFalse(inactive.active)
