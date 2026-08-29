# -*- coding: utf-8 -*-

from odoo import api, models


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    @api.model
    def _hjig_consolidate_legacy_document_control_menu(self):
        """Hide the superseded legacy menu without deleting its records or actions."""
        legacy_menu = self.env.ref(
            "hongyitech_custom.menu_hjig_document_control",
            raise_if_not_found=False,
        )
        if legacy_menu and legacy_menu.active:
            legacy_menu.sudo().write({"active": False})
        return True
