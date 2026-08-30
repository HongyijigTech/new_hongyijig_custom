"""Seed source-linked SOP guidance into the protected master catalogue once."""

from pathlib import Path
from xml.etree import ElementTree

from odoo import SUPERUSER_ID, api
from odoo.exceptions import ValidationError


GUIDANCE_FIELDS = {
    "source_document_name",
    "source_page_from",
    "source_page_to",
    "employee_quick_guide",
    "entry_control_summary",
    "hard_stop_summary",
    "exit_control_summary",
}


def _guidance_values_by_code():
    data_path = Path(__file__).resolve().parents[2] / "data" / "governance_master_data.xml"
    root = ElementTree.parse(data_path).getroot()
    result = {}
    for record in root.findall("record"):
        record_id = record.attrib.get("id", "")
        if not record_id.startswith("artifact_sop_"):
            continue
        fields = {
            field.attrib["name"]: (field.text or "").strip()
            for field in record.findall("field")
            if field.attrib.get("name") in GUIDANCE_FIELDS
        }
        if set(fields) != GUIDANCE_FIELDS:
            continue
        number = record_id.removeprefix("artifact_sop_")
        if not number.isdigit():
            continue
        code = f"SOP-{int(number):03d}"
        fields["source_page_from"] = int(fields["source_page_from"])
        fields["source_page_to"] = int(fields["source_page_to"])
        result[code] = fields
    return result


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    guidance_by_code = _guidance_values_by_code()
    if len(guidance_by_code) != 14:
        raise ValidationError(
            f"Expected source guidance for 14 B-Series SOP masters; found {len(guidance_by_code)}."
        )

    masters = env["hjig.governance.artifact.master"].search([
        ("code", "in", list(guidance_by_code)),
        ("artifact_type", "=", "sop"),
    ])
    if len(masters) != 14:
        raise ValidationError(
            f"Expected 14 existing B-Series SOP masters; found {len(masters)}."
        )

    for master in masters:
        expected = guidance_by_code[master.code]
        existing_values = [master[field_name] for field_name in GUIDANCE_FIELDS]
        if not any(existing_values):
            master.with_context(install_mode=True).write(expected)
            continue
        mismatches = [
            field_name
            for field_name, expected_value in expected.items()
            if master[field_name] != expected_value
        ]
        if mismatches:
            raise ValidationError(
                f"{master.code} already has controlled guidance that differs in: {', '.join(sorted(mismatches))}."
            )

    not_ready = masters.filtered(lambda item: not item.ai_reference_ready)
    if not_ready:
        raise ValidationError(
            f"B-Series SOP guidance is incomplete after migration: {not_ready.mapped('code')}."
        )
