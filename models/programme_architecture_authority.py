# -*- coding: utf-8 -*-
"""Structural corrections controlled by Constitution v6.11."""

from odoo import _, models
from odoo.exceptions import ValidationError


SOURCE_REFERENCE = "Hongyi_BSeries_Constitution_v2_5_v6_11"
SOURCE_VERSION = "v6.11 / Founder approved 21-Aug-2026"
WEEKLY_CODES = tuple("A-%03d" % number for number in range(26, 32))


class HjigProgrammeTemplateVersion(models.Model):
    _inherit = "hjig.programme.template.version"

    def _sync_founder_approved_architecture(self):
        """Correct stage placement and preserve each weekly authority activity."""
        for version in self:
            if version.state != "draft":
                raise ValidationError(_("Programme architecture may be corrected only on a draft version."))
            if version.execution_mode != "governed_gates":
                continue

            activity_by_master = {}
            for activity in version.activity_line_ids:
                for code in (activity.legacy_master_codes or "").split(","):
                    if code.strip():
                        activity_by_master[code.strip().upper()] = activity

            if version.template_id.code == "LGC":
                activation = version.gate_line_ids.filtered(
                    lambda gate: gate.stage_id.code == "PA-00"
                )[:1]
                a004 = activity_by_master.get("A-004")
                if not activation or not a004:
                    raise ValidationError(_("LaunchGuard Complete requires A-004 and Project Activation."))
                a005 = activity_by_master.get("A-005")
                a004.write({
                    "gate_line_id": activation.id,
                    "sequence": (a005.sequence - 1) if a005 else 35,
                    "authority_source_reference": SOURCE_REFERENCE,
                    "authority_source_version": SOURCE_VERSION,
                })

            if version.template_id.code in ("LGC", "LGV", "TLC"):
                combined = version.activity_line_ids.filtered(
                    lambda activity: set(
                        code.strip().upper()
                        for code in (activity.legacy_master_codes or "").split(",")
                        if code.strip()
                    ) == {"A-026", "A-031"}
                    and "WEEK 1 TO WEEK 6" in (activity.name or "").upper()
                )[:1]
                if not combined:
                    # Idempotent path after the combined source task has already been expanded.
                    represented = {
                        code.strip().upper()
                        for activity in version.activity_line_ids
                        for code in (activity.legacy_master_codes or "").split(",")
                        if code.strip().upper() in WEEKLY_CODES
                    }
                    if represented != set(WEEKLY_CODES):
                        raise ValidationError(
                            _("Programme %s does not contain the complete A-026 to A-031 weekly series.")
                            % version.template_id.code
                        )
                else:
                    base_values = {
                        "version_id": version.id,
                        "gate_line_id": combined.gate_line_id.id,
                        "owner_designation_id": combined.owner_designation_id.id,
                        "approver_designation_id": combined.approver_designation_id.id,
                        "coordinator_designation_id": combined.coordinator_designation_id.id,
                        "support_designation_ids": [(6, 0, combined.support_designation_ids.ids)],
                        "offset_days": combined.offset_days,
                        "duration_days": combined.duration_days,
                        "required_artifact_ids": [(6, 0, combined.required_artifact_ids.ids)],
                        "execution_basis": "mould",
                        "conditional": False,
                        "authority_source_reference": SOURCE_REFERENCE,
                        "authority_source_version": SOURCE_VERSION,
                    }
                    combined.write({
                        "name": "A-026: Manufacturing Updates Report — Week 1",
                        "legacy_master_codes": "A-026",
                        "authority_source_reference": SOURCE_REFERENCE,
                        "authority_source_version": SOURCE_VERSION,
                    })
                    for offset, master_code in enumerate(WEEKLY_CODES[1:], start=1):
                        values = dict(base_values)
                        values.update({
                            "code": "%s-AUTH-%s" % (
                                version.template_id.code,
                                master_code.replace("-", ""),
                            ),
                            "name": "%s: Manufacturing Updates Report — Week %s" % (
                                master_code, offset + 1,
                            ),
                            "sequence": combined.sequence + offset,
                            "legacy_master_codes": master_code,
                        })
                        self.env["hjig.programme.template.activity"].create(values)

            # Preserve a deterministic route order after inserting controlled activities.
            activities = version.activity_line_ids.sorted(
                lambda item: (item.gate_line_id.sequence, item.sequence, item.id)
            )
            for sequence, activity in enumerate(activities, start=1):
                activity.sequence = sequence * 10
        return True
