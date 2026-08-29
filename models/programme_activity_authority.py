# -*- coding: utf-8 -*-
"""Founder-approved activity authority from the locked B-Series Constitution."""

import re

from odoo import _, models
from odoo.exceptions import ValidationError


SOURCE_REFERENCE = "Hongyi_BSeries_Constitution_v2_5_v6_11"
SOURCE_VERSION = "v6.11 / Founder approved 21-Aug-2026"


OWNER_CODE_GROUPS = (
    ("PROJECT-COORD", "A-001 A-002 A-003 A-006 A-013 A-018 A-038 A-042 A-043 A-049 A-053 A-092 B8-06 B8-07 B8-09"),
    ("SR-TOOL-DESIGN", "A-004 A-007 A-008 A-009 A-010 A-011 A-012 A-019 A-020 A-021 A-022 A-024 A-039 A-040 A-041 A-044 A-050 A-051 A-052 A-055A A-055B A-057 A-061 A-062 A-063 A-087 A-089"),
    ("PROJECT-MANAGER", "A-005 B8-04 B8-05 B8-08"),
    ("VENDOR-SOURCING", "A-014 A-015 A-016 A-017"),
    ("SR-TOOL-DEVELOPMENT", "A-023 A-025 A-032 A-033 A-045 A-046 A-054 A-055 A-058 A-059 A-060 A-064 A-065 A-066 A-067 A-085 A-086 A-088 A-090 B8-01 B8-02"),
    ("SR-DEVELOPMENT-CHINA", "A-026 A-027 A-028 A-029 A-030 A-031 A-034 A-035 A-036 A-037 A-047 A-048 A-056"),
    ("COMMERCIAL-LOGISTICS", "A-068 A-069 A-070 A-071 A-072 A-073 A-074 A-075 A-076 A-077 A-078 A-079 A-080 A-081 A-082 A-083 A-084 A-091 B8-03 CM-01 CM-02 CM-03 CM-04 CM-05 CM-06 CM-07 CM-08 CM-09 CM-10 CM-11"),
)

OWNER_BY_MASTER_CODE = {
    master_code: designation_code
    for designation_code, master_codes in OWNER_CODE_GROUPS
    for master_code in master_codes.split()
}

# A-005 owns the controlled Risk Register. The approved FRM-006 authority
# separates its Project Manager owner from PMO document-control approval.
APPROVER_BY_MASTER_CODE = {
    "A-005": "PMO-DOC",
}

ACCOUNTING_SUPPORT_CODES = {
    "A-091", "CM-01", "CM-02", "CM-03", "CM-04", "CM-05", "CM-06",
    "CM-07", "CM-08", "CM-09", "CM-10", "CM-11",
}

MASTER_CODE_PATTERN = re.compile(r"\b(?:A-\d{3}[A-Z]?|B8-\d{2}|CM-\d{2})\b", re.IGNORECASE)


def _master_codes(activity):
    codes = {
        code.strip().upper()
        for code in (activity.legacy_master_codes or "").split(",")
        if code.strip()
    }
    codes.update(code.upper() for code in MASTER_CODE_PATTERN.findall(activity.name or ""))
    return codes


class HjigProgrammeTemplateVersion(models.Model):
    _inherit = "hjig.programme.template.version"

    def _sync_founder_approved_activity_authority(self):
        """Apply the locked activity-by-activity owner table to draft programme DNA."""
        Designation = self.env["hjig.governance.designation"]
        required_codes = set(OWNER_BY_MASTER_CODE.values()) | set(APPROVER_BY_MASTER_CODE.values()) | {
            "PROJECT-COORD", "ACCOUNTING-PAYMENTS",
        }
        designations = {
            designation.code: designation
            for designation in Designation.search([("code", "in", sorted(required_codes))])
        }
        missing = required_codes - set(designations)
        if missing:
            raise ValidationError(
                _("Missing controlled activity designations: %s") % ", ".join(sorted(missing))
            )

        for version in self:
            if version.state != "draft":
                raise ValidationError(_("Activity authority may be synchronised only on a draft version."))
            if version.execution_mode != "governed_gates":
                continue
            for activity in version.activity_line_ids:
                codes = _master_codes(activity)
                owner_codes = {OWNER_BY_MASTER_CODE[code] for code in codes if code in OWNER_BY_MASTER_CODE}
                approver_codes = {
                    APPROVER_BY_MASTER_CODE[code]
                    for code in codes
                    if code in APPROVER_BY_MASTER_CODE
                }
                if len(owner_codes) > 1:
                    if "REPLACES" not in (activity.name or "").upper():
                        raise ValidationError(
                            _("One activity combines controlled codes with conflicting owners: %s")
                            % activity.name
                        )
                if len(approver_codes) > 1:
                    raise ValidationError(
                        _("One activity combines controlled codes with conflicting approvers: %s")
                        % activity.name
                    )
                values = {
                    "coordinator_designation_id": designations["PROJECT-COORD"].id,
                    "authority_source_reference": SOURCE_REFERENCE,
                    "authority_source_version": SOURCE_VERSION,
                }
                if len(owner_codes) == 1:
                    values["owner_designation_id"] = designations[owner_codes.pop()].id
                if len(approver_codes) == 1:
                    values["approver_designation_id"] = designations[approver_codes.pop()].id
                support_codes = set()
                if len(owner_codes) > 1:
                    # A programme-specific replacement keeps its explicit accountable
                    # owner and carries every replaced activity owner as visible support.
                    support_codes.update(owner_codes)
                if codes & ACCOUNTING_SUPPORT_CODES:
                    support_codes.add("ACCOUNTING-PAYMENTS")
                if "A-017" in codes:
                    support_codes.add("PROJECT-COORD")
                values["support_designation_ids"] = [
                    (6, 0, [designations[code].id for code in sorted(support_codes)])
                ]
                activity.write(values)
        return True
