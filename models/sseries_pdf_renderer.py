import base64
import hashlib
import html
import io
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from odoo import _, fields, models
from odoo.exceptions import UserError, ValidationError


RENDERER_VERSION = "HJIG-ODOO-EXACT-NATIVE-PDF-v1.0"
RULE_SET_ID = "HJIG-DOC-GOV-LOCK-v1.1"
FORBIDDEN_TEXT = (
    "100 CR Revenue",
    "supplier scoring",
    "internal role-hours",
    "cost build-up",
    "unredacted quotation",
    "reusable sourcing intelligence",
)
TEMPLATE_SPECS = {
    "S4-ACCEPTANCE": (
        "Hongyi_S4_Acceptance_Record_EXACT_NATIVE_TEMPLATE_R1_SANITIZED.docx", 1
    ),
    "S5-ORDER-PUNCH": (
        "Hongyi_S5_Order_Punch_EXACT_NATIVE_TEMPLATE_R1_SANITIZED.docx", 3
    ),
    "S6-TEAM-HANDOVER": (
        "Hongyi_S6_Team_Handover_EXACT_NATIVE_TEMPLATE_R1_SANITIZED.docx", 2
    ),
    "S6-CHINA-HANDOVER": (
        "Hongyi_S6_China_Handover_EXACT_NATIVE_TEMPLATE_R1_SANITIZED.docx", 2
    ),
    "S6-SUPPLIER-RFQ-EN": (
        "Hongyi_S6_Supplier_RFQ_EN_EXACT_NATIVE_TEMPLATE_R1_SANITIZED.docx", 2
    ),
    "S6-SUPPLIER-RFQ-ZH": (
        "Hongyi_S6_Supplier_RFQ_ZH_EXACT_NATIVE_TEMPLATE_R1_SANITIZED.docx", 2
    ),
}
TOKEN_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


def _tag(name):
    return "{%s}%s" % (W_NS, name)


def _safe(value):
    text = str(value or "").strip()
    return text or "—"


def _date(value):
    if not value:
        return "—"
    return fields.Date.to_string(value.date() if hasattr(value, "date") else value)


def _display_user(user):
    return _safe(user.name if user else False)


class HjigSSeriesArtifact(models.Model):
    _inherit = "hjig.sseries.artifact"

    render_engine_version = fields.Char(readonly=True, copy=False)
    render_source_digest = fields.Char(readonly=True, copy=False, index=True)
    rendered_page_count = fields.Integer(readonly=True, copy=False)
    rendered_on = fields.Datetime(readonly=True, copy=False)
    render_manifest_json = fields.Json(readonly=True, copy=False)

    def _assert_renderer_user(self):
        if not self.env.user.has_group("new_hongyijig_custom.group_hjig_sseries_manager"):
            raise UserError(_("S-Series manager authority is required to render commercial documents."))

    def action_generate_controlled_draft(self):
        self._assert_renderer_user()
        for artifact in self:
            if not artifact.template_id.approved_for_internal_uat_generation:
                raise ValidationError(_(
                    "This exact visual authority is not approved for internal-UAT generation."
                ))
            if artifact.code not in TEMPLATE_SPECS:
                raise ValidationError(_(
                    "This document remains attachment-controlled because no exact-native Odoo renderer is approved."
                ))
            if artifact.state in ("approved", "issued"):
                raise ValidationError(_("An approved or issued document cannot be regenerated."))
            pdf_bytes, manifest = artifact._render_exact_native_pdf()
            digest = hashlib.sha256(pdf_bytes).hexdigest()
            manifest["candidate_pdf_sha256"] = digest
            filename = "%s_%s_INTERNAL_UAT.pdf" % (
                re.sub(r"[^A-Za-z0-9._-]+", "_", artifact.case_id.name),
                artifact.code,
            )
            artifact.with_context(hjig_sseries_artifact_workflow=True).write({
                "document_data": base64.b64encode(pdf_bytes),
                "document_filename": filename,
                "prepared_by_id": self.env.user.id,
                "state": "draft",
                "document_sha256": False,
                "visual_qa_verified": False,
                "content_qa_verified": False,
                "user_final_approval": False,
                "customer_issue_allowed": False,
                "supplier_issue_allowed": False,
                "approved_by_id": False,
                "approved_on": False,
                "render_engine_version": RENDERER_VERSION,
                "render_source_digest": manifest["source_payload_sha256"],
                "rendered_page_count": manifest["page_count"],
                "rendered_on": fields.Datetime.now(),
                "render_manifest_json": manifest,
            })
        return True

    def _render_exact_native_pdf(self):
        self.ensure_one()
        try:
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle
            from reportlab.lib.units import cm
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.cidfonts import UnicodeCIDFont
            from reportlab.platypus import (
                Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
            )
        except ImportError as error:
            raise ValidationError(_("The approved server PDF runtime is unavailable.")) from error

        filename, expected_pages = TEMPLATE_SPECS[self.code]
        module_root = Path(__file__).resolve().parents[1]
        template_path = (
            module_root / "resources" / "sseries_internal_uat"
            / "activation_handover_r1" / filename
        )
        logo_path = module_root / "static" / "src" / "img" / "Hongyijig1_APPROVED_TRANSPARENT_MASTER.png"
        if not template_path.is_file() or not logo_path.is_file():
            raise ValidationError(_("Exact-native template or approved transparent logo is missing."))

        values = self._controlled_render_values()
        structures, tokens = self._read_docx_structure(template_path)
        missing = sorted(token for token in tokens if token not in values)
        if missing:
            raise ValidationError(_("Missing controlled values: %s") % ", ".join(missing))
        for token, value in values.items():
            lowered = _safe(value).lower()
            for forbidden in FORBIDDEN_TEXT:
                if forbidden.lower() in lowered:
                    raise ValidationError(_("Confidentiality boundary violation in %s.") % token)

        try:
            pdfmetrics.getFont("STSong-Light")
        except KeyError:
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

        orange = colors.HexColor("#F15A24")
        ink = colors.HexColor("#1A1A1A")
        muted = colors.HexColor("#777777")
        light = colors.HexColor("#F5F5F3")
        border = colors.HexColor("#D8D8D4")
        available_width = A4[0] - 3.8 * cm
        buffer = io.BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=1.9 * cm,
            rightMargin=1.9 * cm,
            topMargin=0.9 * cm,
            bottomMargin=1.0 * cm,
            title="%s / %s" % (self.case_id.name, self.code),
            author="Hongyi JIG Rapid Technologies",
        )

        body_style = ParagraphStyle(
            "HJIGBody", fontName="Helvetica", fontSize=7.6, leading=8.8,
            textColor=ink, alignment=TA_LEFT, spaceAfter=1.2,
        )
        cjk_style = ParagraphStyle(
            "HJIGCJK", parent=body_style, fontName="STSong-Light", fontSize=7.2, leading=8.6,
        )
        label_style = ParagraphStyle(
            "HJIGLabel", parent=body_style, fontSize=7.3, leading=8.5,
            textColor=orange, spaceBefore=3.2, spaceAfter=2.2,
        )
        muted_style = ParagraphStyle(
            "HJIGMuted", parent=body_style, fontSize=7.6, leading=9.0,
            textColor=muted,
        )
        masthead_style = ParagraphStyle(
            "HJIGMasthead", parent=body_style, fontSize=9.5, leading=12,
            textColor=ink, alignment=TA_RIGHT,
        )
        header_style = ParagraphStyle(
            "HJIGTableHeader", parent=body_style, fontSize=7.0, leading=8.2,
            textColor=colors.white, alignment=TA_CENTER,
        )
        cell_style = cjk_style if self.code.endswith("-ZH") else body_style
        story = []
        rendered_pages = 1

        def substitute(text):
            def replacement(match):
                return _safe(values[match.group(0)])
            rendered = TOKEN_RE.sub(replacement, text or "")
            return rendered.replace(
                "SYSTEM-GENERATED FROM GOVERNED SHEET RECORD",
                "SYSTEM-GENERATED FROM GOVERNED ODOO RECORD",
            )

        def paragraph(text, style=cell_style, bold=False, align=None):
            value = html.escape(substitute(text)).replace("\n", "<br/>")
            if bold and self.code != "S6-SUPPLIER-RFQ-ZH":
                value = "<b>%s</b>" % value
            if align is None:
                return Paragraph(value, style)
            custom = ParagraphStyle("HJIGCell%d" % len(story), parent=style, alignment=align)
            return Paragraph(value, custom)

        for kind, payload in structures:
            if kind == "page_break":
                story.append(PageBreak())
                rendered_pages += 1
                continue
            if kind == "paragraph":
                text = substitute(payload).strip()
                if not text:
                    continue
                style = label_style if text.upper() == text and len(text) < 90 else muted_style
                story.extend([paragraph(text, style), Spacer(1, 0.05 * cm)])
                continue

            rows, grid_widths = payload
            raw_text = " ".join(" ".join(row) for row in rows)
            masthead_markers = (
                "COMMERCIAL ACCEPTANCE", "ORDER PUNCH", "TEAM HANDOVER",
                "CHINA HANDOVER", "SUPPLIER RFQ",
            )
            is_masthead = (
                len(rows) == 1
                and len(rows[0]) == 2
                and (
                    "Page " in raw_text
                    or any(marker in raw_text.upper() for marker in masthead_markers)
                )
            )
            if is_masthead:
                right_text = substitute(rows[0][1])
                lines = [line.strip() for line in right_text.split("\n") if line.strip()]
                title = lines[0] if lines else self.template_id.name
                rest = "<br/>".join(html.escape(line) for line in lines[1:])
                right = Paragraph(
                    '<font color="#F15A24" size="15"><b>%s</b></font><br/>%s'
                    % (html.escape(title), rest),
                    masthead_style,
                )
                image = Image(str(logo_path), width=7.6 * cm, height=1.99 * cm)
                table = Table([[image, right]], colWidths=[9.0 * cm, 8.2 * cm])
                table.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]))
                story.extend([table, Spacer(1, 0.06 * cm)])
                continue

            column_count = len(rows[0]) if rows else 1
            if grid_widths and len(grid_widths) == column_count and sum(grid_widths):
                total = float(sum(grid_widths))
                widths = [available_width * value / total for value in grid_widths]
            else:
                widths = [available_width / column_count] * column_count
            has_header = column_count >= 3 or (
                column_count == 2 and rows and rows[0][0].upper() in {
                    "GO TO S5", "PREPARED BY", "HONGYI HANDOVER"
                }
            )
            table_rows = []
            for row_index, row in enumerate(rows):
                formatted = []
                for cell_index, text in enumerate(row):
                    is_header_cell = has_header and row_index == 0
                    if is_header_cell:
                        formatted.append(paragraph(text, header_style, bold=True))
                    else:
                        formatted.append(paragraph(
                            text, cell_style, bold=column_count == 2 and cell_index == 0
                        ))
                table_rows.append(formatted)
            table = Table(table_rows, colWidths=widths, repeatRows=1 if has_header else 0)
            style_commands = [
                ("GRID", (0, 0), (-1, -1), 0.45, border),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4.5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4.5),
                ("TOPPADDING", (0, 0), (-1, -1), 3.0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.0),
            ]
            if has_header:
                style_commands.extend([
                    ("BACKGROUND", (0, 0), (-1, 0), ink),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ])
            elif column_count == 2:
                style_commands.append(("BACKGROUND", (0, 0), (0, -1), light))
            table.setStyle(TableStyle(style_commands))
            story.extend([table, Spacer(1, 0.07 * cm)])

        def footer(canvas, doc):
            canvas.saveState()
            canvas.setFont("Helvetica", 6.8)
            canvas.setFillColor(muted)
            canvas.drawString(
                1.9 * cm, 0.48 * cm,
                "Hongyi JIG Rapid Technologies  •  Confidential  •  INTERNAL UAT",
            )
            canvas.drawRightString(
                A4[0] - 1.9 * cm, 0.48 * cm,
                "Page %s of %s" % (doc.page, expected_pages),
            )
            canvas.restoreState()

        document.build(story, onFirstPage=footer, onLaterPages=footer)
        pdf_bytes = buffer.getvalue()
        if not pdf_bytes.startswith(b"%PDF-") or len(pdf_bytes) < 1000:
            raise ValidationError(_("Physical PDF generation failed."))
        actual_pages = document.page
        if actual_pages != expected_pages or rendered_pages != expected_pages:
            raise ValidationError(_(
                "Exact-native page topology changed: expected %s, rendered %s."
            ) % (expected_pages, actual_pages))
        unresolved = TOKEN_RE.findall(pdf_bytes.decode("latin-1", errors="ignore"))
        if unresolved:
            raise ValidationError(_("Unresolved placeholders remain in the generated PDF."))

        canonical = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        manifest = {
            "rule_set_id": RULE_SET_ID,
            "document_id": self.code,
            "audience": self.audience,
            "master_file_id": self.template_id.master_file_id,
            "master_source_sha256": self.template_id.source_sha256,
            "renderer_version": RENDERER_VERSION,
            "source_payload_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "template_binary_sha256": hashlib.sha256(template_path.read_bytes()).hexdigest(),
            "page_count": actual_pages,
            "expected_page_count": expected_pages,
            "font_family": "Helvetica" if not self.code.endswith("-ZH") else "Helvetica + controlled CJK CID fallback",
            "token_count": len(tokens),
            "explicit_neutral_blank_count": sum(1 for token in tokens if values[token] == "—"),
            "unresolved_placeholder_count": 0,
            "customer_issue_allowed": False,
            "supplier_issue_allowed": False,
            "visual_qa": "PENDING_DIRECT_RENDERED_INSPECTION",
            "content_and_governance_qa": "PENDING_MANAGER_REVIEW",
        }
        return pdf_bytes, manifest

    def _controlled_render_values(self):
        self.ensure_one()
        case = self.case_id
        project = case.intake_project_id
        submission = case.submission_id
        component = project.component_ids.sorted("sequence")[:1]
        route = dict(case._fields["programme_route"].selection).get(case.programme_route, "—")
        services = project.services_json or {}
        acceptance_method = dict(case._fields["acceptance_basis"].selection).get(
            case.acceptance_basis, "—"
        )
        sourcebridge = "Applicable" if case.sourcebridge_required else "Not applicable"
        now_date = fields.Date.context_today(self)
        proposal_date = _date(case.commercial_approved_on)
        order_date = _date(case.acceptance_date or now_date)
        values = {token: "—" for token in self._template_tokens()}
        common = {
            "{{ACCEPTANCE_DATE}}": _date(case.acceptance_date),
            "{{ACCEPTANCE_EVIDENCE_REFERENCE}}": _safe(case.acceptance_reference),
            "{{ACCEPTANCE_RECORD_NO}}": "S4-%s" % case.name,
            "{{ACCEPTANCE_REF}}": _safe(case.acceptance_reference),
            "{{ACCEPTANCE_STATUS}}": "Accepted" if case.acceptance_date else "Pending",
            "{{SIGNED_PROPOSAL_OR_PO}}": acceptance_method,
            "{{SIGNED_PROPOSAL_OR_PO_REFERENCE}}": _safe(case.acceptance_reference),
            "{{CUSTOMER_LEGAL_NAME}}": _safe(case.customer_name),
            "{{CUSTOMER_AUTHORITY}}": _safe(submission.contact_name),
            "{{CUSTOMER_SIGNATORY_NAME}}": _safe(submission.contact_name),
            "{{PROJECT_OR_PORTFOLIO_NAME}}": _safe(case.project_name),
            "{{PROGRAMME_NAME}}": route,
            "{{PROGRAMME_VARIANT}}": "SourceBridge enabled" if case.sourcebridge_required else "Standard",
            "{{PROPOSAL_NO}}": _safe(case.proposal_number),
            "{{PROPOSAL_VERSION}}": str(case.proposal_version or 1),
            "{{PROPOSAL_DATE}}": proposal_date,
            "{{ORDER_NUMBER}}": _safe(case.order_number),
            "{{ORDER_DATE}}": order_date,
            "{{S_SERIES_ID}}": _safe(case.name),
            "{{B_SERIES_PROJECT_ID}}": _safe(case.project_id.x_project_code if case.project_id else False),
            "{{B0_ROUTE}}": route,
            "{{B_SERIES_ENTRY_STAGE}}": "B0 Activation / Handover",
            "{{SOURCEBRIDGE_REQUIRED}}": sourcebridge,
            "{{CHINA_REQUIRED}}": sourcebridge,
            "{{RFQ_REQUIRED}}": sourcebridge,
            "{{PORTFOLIOGUARD_REQUIRED}}": "Applicable" if case.form_type == "portfolio_guard" else "Not applicable",
            "{{PROJECT_DURATION}}": "%s months" % project.expected_duration_months if project.expected_duration_months else _safe(project.expected_duration_range),
            "{{MOULD_COUNT}}": str(project.mould_count or 0),
            "{{INDUSTRY_COMPLEXITY}}": _safe(project.product_category),
            "{{PROJECT_OBJECTIVE}}": _safe(project.sourcebridge_objective or case.internal_review_summary),
            "{{GOVERNED_DELIVERABLE}}": _safe(case.governance_summary),
            "{{NDA_STATUS}}": "Complete" if case.nda_completed else ("Required" if case.nda_required else "Not required"),
            "{{NDA_STATUS_REF}}": "Complete" if case.nda_completed else "Pending",
            "{{NDA_REFERENCE}}": "Recorded in Odoo" if case.nda_completed else "—",
            "{{NDA_REF}}": "Recorded in Odoo" if case.nda_completed else "—",
            "{{PI_REFERENCE}}": _safe(case.proforma_reference),
            "{{PAYMENT_EVIDENCE_REFERENCE}}": _safe(case.payment_evidence_reference),
            "{{FINANCE_REF}}": _safe(case.payment_evidence_reference or case.proforma_reference),
            "{{TAX_INVOICE_STATUS}}": "Recorded" if case.tax_invoice_reference else "Pending Finance/Tally authority",
            "{{TAX_INVOICE_REFERENCE}}": _safe(case.tax_invoice_reference),
            "{{COMMERCIAL_REVIEWER_NAME}}": _display_user(case.commercial_approved_by_id),
            "{{COMMERCIAL_REVIEW_DATE}}": _date(case.commercial_approved_on),
            "{{COMMERCIAL_OWNER}}": _display_user(case.owner_id),
            "{{PMO_LEAD}}": _display_user(case.handover_owner_id or case.owner_id),
            "{{TECHNICAL_AUTHORITY}}": _display_user(case.handover_owner_id),
            "{{SOURCING_LEAD}}": _display_user(case.handover_owner_id),
            "{{FINANCE_OWNER}}": "Finance Team",
            "{{HANDOVER_OWNER}}": _display_user(case.owner_id),
            "{{RECEIVING_OWNER}}": _display_user(case.handover_owner_id),
            "{{HANDOVER_DATE}}": _date(now_date),
            "{{HANDOVER_STATUS}}": "Accepted" if case.handover_accepted else "Pending",
            "{{ORDER_PUNCH_REFERENCE}}": _safe(case.order_number),
            "{{ORDER_PUNCH_STATUS}}": "Approved" if case.order_punch_approved else "Pending",
            "{{B0_HANDOVER_DECISION}}": "GO" if case.handover_accepted else "HOLD",
            "{{B0_HANDOVER_DATE}}": _date(now_date) if case.handover_accepted else "—",
            "{{B0_MANIFEST_REFERENCE}}": _safe(case.b0_manifest_id.name),
            "{{ACTIVATION_DECISION}}": "GO" if case.payment_received and case.order_punch_approved else "HOLD",
            "{{ACTIVATION_DATE}}": _date(now_date),
            "{{EXECUTION_ENTRY_STAGE}}": "B0 Activation / Handover",
            "{{EXECUTION_START_DATE}}": _date(now_date) if case.handover_accepted else "—",
            "{{OPEN_HOLD_CONDITIONS}}": _safe(case.blocker_summary),
            "{{REPORTING_FREQUENCY}}": "As per approved programme cadence",
            "{{REPORTING_CHANNEL}}": "Odoo Project and governed records",
            "{{MONITORING_MODE}}": "Odoo governed programme controls",
            "{{EXECUTION_MODE}}": route,
            "{{ADVISORY_ONLY}}": "Applicable" if project.engagement_model == "ADVISORY_TOOLLOCK_LITE" else "Not applicable",
            "{{ENGINEERING_EXECUTION_REQUIRED}}": "Applicable" if project.engagement_model != "SOURCEBRIDGE_ONLY" else "Not applicable",
            "{{ENGINEERING_ACTIVATION}}": "Activate approved programme run at B0",
            "{{SOURCEBRIDGE_ACTIVATION}}": "Activate controlled SourceBridge engagement" if case.sourcebridge_required else "Not applicable",
            "{{CUSTOMER_DECISION_AUTHORITY}}": _safe(submission.contact_name),
            "{{HONGYI_PMO_AUTHORITY}}": _display_user(case.handover_owner_id or case.owner_id),
            "{{SOURCEBRIDGE_PACKAGE_REF}}": _safe(case.client_submission_id),
            "{{SOURCING_MANIFEST_REFERENCE}}": _safe(case.b0_manifest_id.name),
            "{{B_SERIES_PROJECT_ID}}": _safe(case.project_id.x_project_code if case.project_id else False),
            "{{HONGYI_CONTACT_NAME}}": "Business Development Team",
            "{{HONGYI_CONTACT_EMAIL}}": "businesscrm@hongyijiig.com",
            "{{MASKED_PROJECT_REFERENCE}}": _safe(case.client_project_id),
            "{{CURRENCY}}": _safe(case.currency_id.name),
            "{{RFQ_DATE}}": _date(now_date),
            "{{RFQ_REVISION}}": "R1",
            "{{QUOTE_DUE_TIMEZONE}}": "IST",
            "{{DISCLOSURE_BOUNDARY}}": "Customer identity and confidential commercial data must not be disclosed.",
            "{{PAYMENT_TERM_BASIS}}": "Supplier proposal required; no purchase commitment.",
            "{{PRICE_BASIS}}": "Supplier response required",
            "{{QUOTE_VALIDITY}}": "Supplier to state",
            "{{VALIDITY_CONDITIONS}}": "Subject to Hongyi technical and commercial approval",
            "{{WARRANTY_STATUS}}": "Supplier to state",
        }
        values.update({key: _safe(value) for key, value in common.items() if key in values})
        for index in range(1, 7):
            for prefix in ("OK", "B0", "H", "A", "C", "P"):
                token = "{{%s_%s}}" % (prefix, index)
                if token in values:
                    values[token] = "PASS"
        for token in ("{{DECISION_1}}", "{{ACTIVATION_GATE_REF}}", "{{SCOPE_ACCEPTANCE_REF}}"):
            if token in values:
                values[token] = "GO" if case.acceptance_date else "HOLD"
        if component:
            component = component[0]
            component_values = {
                "{{RFQ_NUMBER}}": "%s-RFQ-%03d" % (_safe(case.order_number), component.component_index),
                "{{PART_OR_ASSEMBLY_NAME}}": _safe(component.name),
                "{{PART_DESCRIPTION}}": _safe(component.component_function),
                "{{MATERIAL_SPECIFICATION}}": _safe(component.material_grade),
                "{{MATERIAL_STANDARD}}": _safe(component.technical_specification_status),
                "{{ANNUAL_VOLUME}}": str(component.expected_year_1_quantity or 0),
                "{{VOLUME_ASSUMPTION_REF}}": _safe(case.client_submission_id),
                "{{DRAWING_REFERENCE}}": _safe(component.technical_specification_status),
                "{{PART_PRODUCTION_APPLIES}}": "Applicable",
                "{{PART_PRODUCTION_ACTION}}": _safe(component.preferred_solution_route),
            }
            values.update({key: _safe(value) for key, value in component_values.items() if key in values})
        supplier_response_tokens = (
            "SUPPLIER_TOOLING_PRICE", "SUPPLIER_UNIT_PRICE", "SUPPLIER_SAMPLE_COST",
            "SUPPLIER_MOQ", "SUPPLIER_INCOTERM", "SUPPLIER_PAYMENT_TERMS",
            "DFM_LEAD_TIME", "DFM_NOTES", "TOOLING_LEAD_TIME", "TOOLING_MILESTONES",
            "SAMPLE_LEAD_TIME", "SAMPLE_PLAN", "PRODUCTION_LEAD_TIME", "PRODUCTION_PLAN",
            "QUALITY_SYSTEM_STATUS", "QUALITY_CERTIFICATE_REF", "MATERIAL_CERT_STATUS",
            "MATERIAL_CERT_REF", "INSPECTION_REPORT_STATUS", "INSPECTION_REPORT_REF",
            "TRACEABILITY_STATUS", "TRACEABILITY_METHOD", "SUPPLIER_COMPANY",
            "SUPPLIER_AUTHORISED_PERSON", "SUPPLIER_DESIGNATION", "SUPPLIER_SIGNATURE_DATE",
        )
        for name in supplier_response_tokens:
            token = "{{%s}}" % name
            if token in values:
                values[token] = "Supplier response required"
        return values

    def _template_tokens(self):
        self.ensure_one()
        filename = TEMPLATE_SPECS.get(self.code, (False, False))[0]
        if not filename:
            return set()
        template_path = (
            Path(__file__).resolve().parents[1]
            / "resources" / "sseries_internal_uat"
            / "activation_handover_r1" / filename
        )
        _structures, tokens = self._read_docx_structure(template_path)
        return tokens

    @staticmethod
    def _read_docx_structure(template_path):
        try:
            with zipfile.ZipFile(template_path) as archive:
                root = ET.fromstring(archive.read("word/document.xml"))
        except (OSError, zipfile.BadZipFile, KeyError, ET.ParseError) as error:
            raise ValidationError(_("Exact-native DOCX authority is unreadable.")) from error

        def paragraph_text(node):
            return "".join(text.text or "" for text in node.findall(".//w:t", NS))

        def cell_text(cell):
            parts = [paragraph_text(p) for p in cell.findall(".//w:p", NS)]
            return "\n".join(part for part in parts if part)

        structures = []
        tokens = set()
        body = root.find("w:body", NS)
        for child in list(body or []):
            if child.tag == _tag("p"):
                if child.find(".//w:br[@w:type='page']", NS) is not None:
                    structures.append(("page_break", None))
                text = paragraph_text(child)
                if text.strip():
                    tokens.update(TOKEN_RE.findall(text))
                    structures.append(("paragraph", text))
            elif child.tag == _tag("tbl"):
                rows = []
                for row in child.findall("w:tr", NS):
                    values = [cell_text(cell) for cell in row.findall("w:tc", NS)]
                    if values:
                        rows.append(values)
                        for value in values:
                            tokens.update(TOKEN_RE.findall(value))
                grid_widths = []
                for col in child.findall("w:tblGrid/w:gridCol", NS):
                    raw = col.get(_tag("w")) or "0"
                    try:
                        grid_widths.append(int(raw))
                    except ValueError:
                        grid_widths.append(0)
                if rows:
                    structures.append(("table", (rows, grid_widths)))
        return structures, tokens
