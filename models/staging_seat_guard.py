# -*- coding: utf-8 -*-

from odoo import _, api, models
from odoo.exceptions import ValidationError


class ResUsers(models.Model):
    _inherit = "res.users"

    _HJIG_STAGING_SEAT_GUARD = "new_hongyijig_custom.staging_single_internal_user_guard"

    def _hjig_check_staging_internal_user_limit(self):
        enabled = self.env["ir.config_parameter"].sudo().get_param(
            self._HJIG_STAGING_SEAT_GUARD, "0"
        )
        if enabled not in ("1", "true", "True"):
            return
        active_internal_count = self.with_context(active_test=False).sudo().search_count([
            ("active", "=", True),
            ("share", "=", False),
        ])
        if active_internal_count > 1:
            raise ValidationError(_(
                "Staging is restricted to one active internal Odoo login. "
                "Use a Governance Designation or Planned Team Resource instead of creating "
                "or activating another internal user."
            ))

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        users._hjig_check_staging_internal_user_limit()
        return users

    def write(self, vals):
        result = super().write(vals)
        if {"active", "share", "group_ids"}.intersection(vals):
            self._hjig_check_staging_internal_user_limit()
        return result
