# -*- coding: utf-8 -*-

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestUiCompatibility(TransactionCase):

    def test_legacy_document_control_menu_is_consolidated_when_present(self):
        legacy_menu = self.env.ref(
            "hongyitech_custom.menu_hjig_document_control",
            raise_if_not_found=False,
        )
        if legacy_menu:
            self.assertFalse(legacy_menu.active)

    def test_inspection_routes_have_distinct_names(self):
        governed_action = self.env.ref("new_hongyijig_custom.action_hjig_inspection")
        native_action = self.env.ref("new_hongyijig_custom.action_hjig_inspection_report")
        self.assertEqual(governed_action.name, "SOR-Linked Inspections")
        self.assertEqual(native_action.name, "Visual / Assembly / Dimensional Reports")
