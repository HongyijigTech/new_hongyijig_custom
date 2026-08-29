# -*- coding: utf-8 -*-
import re

from odoo import models


SOURCE_REFERENCE = "Hongyi_BSeries_TG_Gate_Forms_v1_9"
SOURCE_VERSION = "v1.9 / Controlled Updated / 21-Aug-2026"

GATE_FORM_EXIT_ITEMS = (
    ("TG-01", 1, "[LAUNCHGUARD COMPLETE + LAUNCHGUARD DESIGN ONLY] Post-Design Revision confirmed: SOR revised + BOP revised + Design Challenges revised + Mould Planning revised — all re-signed after A-011 Design Sign-Off\nMandatory revision after R&D. B2 cannot begin until all four revised documents are signed off."),
    ("TG-01", 2, "Engraving specification confirmed and documented"),
    ("TG-01", 3, "Mould list LOCKED — moulds, cavity count, family mould decisions finalised (A-012)"),
    ("TG-01", 4, "NDA signed by BOTH parties — HJIG and Customer"),
    ("TG-01", 5, "Solicitation Agreement signed by BOTH parties — HJIG and Customer"),
    ("TG-01", 6, "Updated SOR signed off by customer (A-013)"),
    ("TG-01", 7, "Toolmaker RFQ Package issued (A-014)\nOwner: Vendor & Sourcing Manager"),
    ("TG-01", 8, "Toolmaker shortlist prepared — Cost & Technical Competency comparison done (A-015)\nOwner: Vendor & Sourcing Manager"),
    ("TG-01", 9, "Toolmaker selected and negotiation complete (A-016)\nOwner: Vendor & Sourcing Manager"),
    ("TG-01", 10, "Toolmaker Manufacturing Plan 1 requested"),
    ("TG-01", 11, "Prototyping complete — customer written approval received (within A-009 loop)"),
    ("TG-01", 12, "No open critical design issues without documented resolution plan"),
    ("TG-01", 13, "Risk Register reviewed — no new risk with score ≥16 unresolved\nIf new risk ≥16: document in Risk Register + escalate to PMO before gate closes."),
    ("TG-02", 1, "Client ships reference samples to toolmaker (A-018)\nv2.5 CHANGE: Moved from entry condition to exit condition."),
    ("TG-02", 2, "DFM Sign-Off complete — ALL components (A-019)\nFamily mould: ALL components DFM confirmed. Partial GO not allowed."),
    ("TG-02", 3, "Moldflow Sign-Off complete — ALL components (A-020)\nCONDITIONAL: For small parts where gate change cannot impact steel size, PMO may approve Steel GO before Moldflow. If Moldflow may affect steel size — Moldflow must complete first."),
    ("TG-02", 4, "Tool Design Layout / Construction Concept confirmed (A-021)\nConcept only. Full detailed tool design runs parallel in B3."),
    ("TG-02", 5, "Steel sizes finalised per mould"),
    ("TG-02", 6, "Toolmaker Manufacturing Plan 1 received — includes pre-tooling task timeline"),
    ("TG-02", 7, "CM-04 (30% to Toolmaker) released SIMULTANEOUSLY with Steel GO (A-022)\nSame event. Cannot be separated."),
    ("TG-02", 8, "No unresolved DFM red flags"),
    ("TG-02", 9, "Weekly meeting with toolmaker confirmed and scheduled from B3 entry"),
    ("TG-02", 10, "CM-04 (30% to Toolmaker) payment CONFIRMED RELEASED — simultaneously with Steel GO (A-022)\nTHIS GATE DOES NOT CLOSE UNTIL CM-04 IS CONFIRMED RELEASED. B3 cannot begin without this. Payment must happen AT the gate — not after. If CM-04 is delayed, TG-02 stays open and no B3 activities may begin."),
    ("TG-02", 11, "B3 team briefed and ready — Sr. Tool Development Engineer + Sr. Development Engineer China confirmed available\nPre-tooling team (Sr. Tool Design Engineer) steps back. B3 team now takes over direct interaction with toolmaker in China."),
    ("TG-02", 12, "Risk Register reviewed — no new risk with score ≥16 unresolved\nIf new risk ≥16: document in Risk Register + escalate to PMO before gate closes."),
    ("TG-03", 1, "All machining activities complete (A-025)\nAll manufacturing stages with evidence uploaded for this specific mould."),
    ("TG-03", 2, "Weekly manufacturing reports received — Week 1 to 6 (A-026 to A-031)"),
    ("TG-03", 3, "Polish complete"),
    ("TG-03", 4, "Tool assembly complete"),
    ("TG-03", 5, "Mould Physical Condition Check passed (T-14 / A-032)"),
    ("TG-03", 6, "Mould Physical Condition Check complete (T-14 / A-032)\nPolish complete + Tool assembly complete. Mould painting and surface protection happens at TG-06 (Mould Buyoff) — NOT here."),
    ("TG-03", 7, "CM-05 (Governance Fee: 40% Complete/Control; 35% Development — CORRECTED July 25, 2026) collected from customer — BEFORE T0 trial (A within TG-03)\nActivity within this stage. Must be completed before T0 trial begins. Development percentage was previously mis-stated at CM-06 — now correctly at CM-05."),
    ("TG-03", 8, "Machine availability confirmed at toolmaker for T0 trial (A-034)"),
    ("TG-03", 9, "HJIG resource confirmed for T0 trial — physical OR video (A-035)"),
    ("TG-03", 10, "T0 trial conducted — video/photo evidence received by HJIG (A-036)\nTrial result may be pass or fail. Evidence of trial IS the exit condition."),
    ("TG-03", 11, "No open deviation without documented resolution plan"),
    ("TG-03", 12, "Risk Register reviewed — no new risk with score ≥16 unresolved\nIf new risk ≥16: document in Risk Register + escalate to PMO before gate closes."),
    ("TG-04", 1, "T0 samples shipped to India (A-037)\nSamples must be shipped BEFORE inspection reports are created."),
    ("TG-04", 2, "T0 samples received in India — confirmed (A-038)"),
    ("TG-04", 3, "CM-06 (35% Customer Tooling + 30% to Toolmaker — COMMERCIAL ONLY, no Governance Fee component) collected\nv2.5 CHANGE: CM-06 triggered AFTER A-038 (samples received India) — not before. CM-06 never carries a Governance Fee for any programme (corrected July 25, 2026)."),
    ("TG-04", 4, "Visual Inspection Report created (T-09 / A-039)\nOwner: Sr. Tool Design Engineer. Cannot be created before samples received India."),
    ("TG-04", 5, "Assembly Inspection Report created (T-10 / A-040)\nOwner: Sr. Tool Design Engineer."),
    ("TG-04", 6, "Dimensional Inspection Report created (T-11 / A-041) — CONDITIONAL"),
    ("TG-04", 7, "All reports sent to supplier + customer — consolidated, ONCE (A-042)\nNo piecemeal feedback. One send only."),
    ("TG-04", 8, "Consolidated feedback — Customer + HJIG — sent once to toolmaker (A-043)"),
    ("TG-04", 9, "ECN check complete on all feedback points (A-044)\nIf ECN raised: log in ECN Register, assess tooling impact, PMO approval before correction."),
    ("TG-04", 10, "Tool correction plan agreed in writing (A-045)"),
    ("TG-04", 11, "T1 corrections completed by toolmaker (A-046)"),
    ("TG-04", 12, "T1 trial conducted at China — video/photo evidence received (A-047)\nPhysical attendance OR video evidence — both acceptable."),
    ("TG-04", 13, "Risk Register reviewed — no new risk with score ≥16 unresolved\nIf new risk ≥16: document in Risk Register + escalate to PMO before gate closes."),
    ("TG-05", 1, "T1 samples shipped to India (A-048)"),
    ("TG-05", 2, "T1 samples received in India — confirmed (A-049)"),
    ("TG-05", 3, "All T0 + T1 CRITICAL points CLOSED\nZero exceptions. T0 critical confirmed closed at TG-04. T1 critical (from India review) also closed."),
    ("TG-05", 4, "All T0 + T1 MAJOR points CLOSED or formally WAIVED by customer in writing"),
    ("TG-05", 5, "T1 Visual Inspection Report issued (T-09 / A-050)"),
    ("TG-05", 6, "T1 Assembly Inspection Report issued (T-10 / A-051)"),
    ("TG-05", 7, "T1 Dimensional Inspection Report issued (T-11 / A-052) — CONDITIONAL"),
    ("TG-05", 8, "Customer acknowledgement of T1 issues received (A-053)\nEmail or WhatsApp valid. MANDATORY before CAP requested from toolmaker."),
    ("TG-05", 9, "Corrective Action Plan (CAP) from toolmaker received (T-17 / A-054)\nBasis = customer-acknowledged T1 issues ONLY."),
    ("TG-05", 10, "T1 correction activities complete (A-055)"),
    ("TG-05", 11, "Surface finish grade re-confirmed with BOTH supplier and customer — VDI/SPI code per Mould Planning Sheet\nVerbal confirmation invalid. Email or WhatsApp from customer accepted. Mould Planning Sheet is the reference document."),
    ("TG-05", 12, "Formal instruction issued to toolmaker to apply approved surface finish on mould\nIssued after both supplier and customer alignment confirmed. Basis: Mould Planning Sheet + customer written confirmation."),
    ("TG-05", 13, "T2 trial conducted — video/photo evidence received by HJIG (A-056)\nv2.5 CHANGE: T2 trial is TG-05 exit condition. Physical attendance OR video — both acceptable."),
    ("TG-05", 14, "Risk Register reviewed — no new risk with score ≥16 unresolved\nIf new risk ≥16: document in Risk Register + escalate to PMO before gate closes."),
    ("TG-06", 1, "Customer written sign-off on Golden Sample (T-15 / A-057)\nv2.5 CHANGE: Golden Sample sign-off comes FIRST before reports. Permanent marker. Set 1 customer, Set 2 HJIG."),
    ("TG-06", 2, "ALL open points from T0+T1+T2 — CLOSED or WAIVED with customer signature (per component)"),
    ("TG-06", 3, "Surface finish verified — VDI/SPI grade confirmed (per component)"),
    ("TG-06", 4, "Engraving verified per A-011 specification (per component)"),
    ("TG-06", 5, "Zero critical open points — no exceptions"),
    ("TG-06", 6, "Mould Trial Report complete (T-12/TR / A-058)"),
    ("TG-06", 7, "Mould Cycle Sequence Report verified (T-13/MCI / A-059)"),
    ("TG-06", 8, "Mould Performance & Durability Report complete (T-21/MPD / A-060)"),
    ("TG-06", 9, "Visual Inspection verified complete (T-09 / A-061)"),
    ("TG-06", 10, "Assembly Inspection verified complete (T-10 / A-062)"),
    ("TG-06", 11, "Dimensional Inspection verified complete (T-11 / A-063) — if in scope"),
    ("TG-06", 12, "Mould painting / surface protection complete (A-033)\nApplied after all corrections done and Golden Sample approved. Painting → Anti-rust → Wooden Box is the mandatory sequence."),
    ("TG-06", 13, "Anti-rust treatment applied (A-064)"),
    ("TG-06", 14, "Wooden packing box ordered and confirmed (A-065)\nv2.5 CHANGE: Wooden box moved from B3 to here — after Golden Sample sign-off. 2-4 days lead time."),
    ("TG-06", 15, "Spare components count confirmed and listed (T-16/MCS / A-066)"),
    ("TG-06", 16, "CM-07 demand raised to customer (25% Governance Fee + 30% tooling)"),
    ("TG-06", 17, "Risk Register reviewed — no new risk with score ≥16 unresolved\nIf new risk ≥16: document in Risk Register + escalate to PMO before gate closes."),
    ("TG-07", 1, "Mould Inspection & Dispatch Readiness complete — T-16/MCS (A-067)\nMould separately, Spares separately, Hot Runner + Controllers separately."),
    ("TG-07", 2, "Incoterm confirmed in writing (A-067)\nFOB / CIF / DAP / DDP — verbal invalid."),
    ("TG-07", 3, "Insurance responsibility defined and documented"),
    ("TG-07", 4, "Shipment Governance & Handling Fee agreed in writing (Option B only)"),
    ("TG-07", 5, "Risk transfer point documented and acknowledged"),
    ("TG-07", 6, "Packing List verified by Commercial | Logistic Manager (A-068)"),
    ("TG-07", 7, "Shipment Quote received + PO issued to shipping supplier (A-069/A-070)"),
    ("TG-07", 8, "Logistics team final recheck of packing list at warehouse (A-071)\nConfirmed against all shipping documents before HBL."),
    ("TG-07", 9, "Container Loading — Packing List + CI + HBL descriptions matched (A-072)"),
    ("TG-07", 10, "HBL confirmed → Final Bill of Lading issued (A-073)"),
    ("TG-07", 11, "Original B/L or Telex Release received (A-074)\nWithout B/L or Telex Release — India port will NOT deliver moulds."),
    ("TG-07", 12, "CO (Certificate of Origin) received (A-074)"),
    ("TG-07", 13, "Final Sail Off confirmed — China to India (A-075)"),
    ("TG-07", 14, "Risk Register reviewed — no new risk with score ≥16 unresolved\nIf new risk ≥16: document in Risk Register + escalate to PMO before gate closes."),
    ("TG-08", 1, "Customer informed of ballpark duty amount 1 week before ETA (A-077)"),
    ("TG-08", 2, "BOE Checklist reviewed and verified (A-079)"),
    ("TG-08", 3, "BOE filed to Customs Portal (A-080)"),
    ("TG-08", 4, "CM-08 demand sent to customer — Duty + Clearance + GST (basis BOE Checklist)"),
    ("TG-08", 5, "Customer payment received and verified (A-081)\nHJIG pays agencies ONLY after customer payment confirmed. No exceptions."),
    ("TG-08", 6, "CM-09 complete — HJIG paid: (1) Customs Duty (2) Shipping (3) GST to portal"),
    ("TG-08", 7, "Custom clearance complete"),
    ("TG-08", 8, "Moulds delivered to customer site (A-082)"),
    ("TG-08", 9, "Delivery confirmation received (A-083)"),
    ("TG-08", 10, "Bill of Entry submitted to bank — RBI compliance (A-084)"),
    ("TG-08", 11, "Risk Register reviewed — no new risk with score ≥16 unresolved\nIf new risk ≥16: document in Risk Register + escalate to PMO before gate closes."),
    ("TG-09", 1, "Mould Delivery Verification complete (A-085)\nChecked against China dispatch record. Any discrepancy — immediately to Chinese toolmaker."),
    ("TG-09", 2, "Mould Trial witnessed and documented (A-086)\nHJIG witnesses only. Customer team operates. HJIG does NOT operate mould."),
    ("TG-09", 3, "Issues Report issued per trial per component (A-087)"),
    ("TG-09", 4, "All issues resolved / Correction Plan agreed with Chinese toolmaker (A-088)\nRepair/spare cost = Chinese toolmaker responsibility. HJIG coordinates only."),
    ("TG-09", 5, "Golden Sample comparison done per component (A-089)\nNo sign-off below Golden Sample standard."),
    ("TG-09", 6, "Final Sign-Off per mould + per component (T-20/MIH / A-090)\nCustomer authorised signatory. Name, designation, date."),
    ("TG-09", 7, "CM-10 collected (0% standard. 5% ONLY if held from CM-07 exception — RARE)\nTrigger = A-090 MIH sign-off for this programme (Complete/Development). Most Chinese toolmakers do not accept holding final payment beyond dispatch. Confirm at A-017 NDA/Solicitation."),
    ("TG-09", 8, "Testimonial request made to customer (A-092)\nWhatsApp/Email/Video byte. Mandatory attempt before B8."),
    ("TG-09", 9, "Risk Register reviewed — no new risk with score ≥16 unresolved\nIf new risk ≥16: document in Risk Register + escalate to PMO before gate closes."),
    ("TG-10", 1, "Final Technical Outcome Summary complete (B8-01)\nOwner: Sr. Tool Development Engineer. Refers to Project Planning Sheet. INTERNAL ONLY."),
    ("TG-10", 2, "Tool Performance Snapshot complete (B8-02)\nStability, issues, learnings. Input for future SOR standards."),
    ("TG-10", 3, "Commercial Closure confirmed — No pending claims (B8-03)"),
    ("TG-10", 4, "Internal Profitability Reflection complete (B8-04)\nINTERNAL ONLY. Never shared externally."),
    ("TG-10", 5, "Supplier Performance Reflection + Future Eligibility (T-22 / B8-05)\nINTERNAL ONLY. Preferred / Conditional / Restricted / Blacklisted."),
    ("TG-10", 6, "Lessons Learned + Risk Register formally CLOSED (B8-06)\nJr. PM/PMO fills. Founder approves before filing."),
    ("TG-10", 7, "Programme Effectiveness Review complete (B8-07)"),
    ("TG-10", 8, "Authority Assets archived (B8-08) — testimonial request evidence is required; receipt is not mandatory."),
    ("TG-10", 9, "Project marked CLOSED in Odoo / System (B8-09)"),
    ("TG-10", 10, "CM-11 released — Final 5% to Chinese Toolmaker\nSTANDARD: held until this gate. CASE-TO-CASE EXCEPTION (added July 25, 2026): if the toolmaker refuses to hold this 5% until B8 Closure, an alternate release schedule requires Founder/PMO WRITTEN APPROVAL, documented at A-017 NDA/Solicitation — BEFORE toolmaker finalisation, not discovered afterwards."),
    ("TG-10", 11, "Risk Register reviewed — no new risk with score ≥16 unresolved\nIf new risk ≥16: document in Risk Register + escalate to PMO before gate closes."),
    ("TG-10-LITE", 1, "Dispatch Confirmation Sign-Off complete\nREPLACES A-089 (Golden Sample Comparison) + A-090 (MIH Sign-Off) for ToolLock Control. Customer confirms mould(s) received in acceptable condition after their own transport/customs process. Golden Sample (from A-057) retained as passive reference document only — available to customer for self-verification if a quality dispute arises during their own installation. HJIG does NOT travel to site, does NOT witness installation, and issues no active comparison sign-off."),
    ("TG-10-LITE", 2, "CM-10 collected — trigger = Dispatch Confirmation Sign-Off (NOT A-090, which never occurs for this programme)\n0% standard. 5% ONLY if held from CM-07 exception — RARE."),
    ("TG-10-LITE", 3, "Final Technical Outcome Summary complete (B8-01)\nOwner: Sr. Tool Development Engineer. Refers to Project Planning Sheet. INTERNAL ONLY."),
    ("TG-10-LITE", 4, "Tool Performance Snapshot complete (B8-02)\nStability, issues, learnings. Input for future SOR standards."),
    ("TG-10-LITE", 5, "Commercial Closure confirmed — No pending claims (B8-03)"),
    ("TG-10-LITE", 6, "Internal Profitability Reflection complete (B8-04)\nINTERNAL ONLY. Never shared externally."),
    ("TG-10-LITE", 7, "Supplier Performance Reflection + Future Eligibility (T-22 / B8-05)\nINTERNAL ONLY. Preferred / Conditional / Restricted / Blacklisted."),
    ("TG-10-LITE", 8, "Lessons Learned + Risk Register formally CLOSED (B8-06)\nJr. PM/PMO fills. Founder approves before filing."),
    ("TG-10-LITE", 9, "Programme Effectiveness Review complete (B8-07)"),
    ("TG-10-LITE", 10, "Authority Assets archived (B8-08) — testimonial request evidence is required; receipt is not mandatory."),
    ("TG-10-LITE", 11, "Project marked CLOSED in Odoo / System (B8-09 — Lite)"),
    ("TG-10-LITE", 12, "CM-11 released — Final 5% to Chinese Toolmaker\nSTANDARD: held until this gate. CASE-TO-CASE EXCEPTION: if the toolmaker refuses to hold this 5% until Lite-Closure, an alternate release schedule requires Founder/PMO WRITTEN APPROVAL, documented at A-017 — BEFORE toolmaker finalisation."),
    ("TG-10-LITE", 13, "Risk Register reviewed — no new risk with score ≥16 unresolved\nIf new risk ≥16: document in Risk Register + escalate to PMO before gate closes."),
)

STAGE_DESIGNATIONS = {
    "TG-01": ("SR-PRODUCT-DESIGN", "PROJECT-MANAGER"),
    "TG-02": ("SR-TOOL-DESIGN", "PROJECT-MANAGER"),
    "TG-03": ("SR-TOOL-DEVELOPMENT", "PROJECT-MANAGER"),
    "TG-04": ("QUALITY-INSPECTION", "PROJECT-MANAGER"),
    "TG-05": ("QUALITY-INSPECTION", "PROJECT-MANAGER"),
    "TG-06": ("QUALITY-INSPECTION", "PROJECT-MANAGER"),
    "TG-07": ("COMMERCIAL-LOGISTICS", "PROJECT-MANAGER"),
    "TG-08": ("COMMERCIAL-LOGISTICS", "PROJECT-MANAGER"),
    "TG-09": ("PROJECT-ENGINEER", "CUSTOMER-APPROVER"),
    "TG-10": ("PROJECT-MANAGER", "PMO-DOC"),
    "TG-10-LITE": ("PROJECT-MANAGER", "PMO-DOC"),
    "PRE-B2": ("PROJECT-MANAGER", "PMO-DOC"),
    "LGD-SIGNOFF": ("SR-PRODUCT-DESIGN", "PROJECT-MANAGER"),
}

PROJECT_SCOPE_MARKERS = (
    "CM-", "PAYMENT", "RISK REGISTER", "TEAM BRIEFED", "WEEKLY MEETING",
    "CUSTOMER INFORMED", "BOE ", "BANK", "RBI", "PROJECT MARKED", "COMMERCIAL CLOSURE",
    "PROFITABILITY", "LESSONS LEARNED", "PROGRAMME EFFECTIVENESS", "AUTHORITY ASSETS",
)


EXPLICIT_EVIDENCE_ARTIFACT_RULES = (
    (("LESSONS LEARNED",), "FRM-023"),
    (("RISK REGISTER",), "FRM-006"),
    (("ECN",), "FRM-010"),
    (("VISUAL INSPECTION",), "FRM-011"),
    (("ASSEMBLY INSPECTION",), "FRM-012"),
    (("DIMENSIONAL INSPECTION",), "FRM-013"),
    (("CORRECTIVE ACTION PLAN",), "FRM-036"),
    (("DFM SIGN-OFF", "DFM SIGN OFF"), "FRM-030"),
    (("MOLDFLOW SIGN-OFF", "MOLDFLOW SIGN OFF"), "FRM-031"),
    (("TOOL DESIGN LAYOUT",), "FRM-032"),
    (("WEEKLY MANUFACTURING REPORT",), "FRM-034"),
    (("DISPATCH READINESS",), "FRM-016"),
    (("PACKING LIST",), "FRM-038"),
    (("HBL", "BILL OF LADING", "B/L", "CERTIFICATE OF ORIGIN"), "FRM-040"),
    (("BOE", "BILL OF ENTRY", "CUSTOM CLEARANCE"), "FRM-041"),
    (("DELIVERY CONFIRMATION", "MOULDS DELIVERED TO CUSTOMER SITE"), "FRM-019"),
    (("MOULD DELIVERY VERIFICATION",), "FRM-020"),
    (("MOULD TRIAL WITNESSED",), "FRM-021"),
    (("ISSUES REPORT",), "FRM-042"),
)


STAGE_MASTER_GATE_ARTIFACTS = {
    "PA-00": "IG-01-G01",
    "LGD-SIGNOFF": "FRM-B2-G01",
    "PRE-B2": "FRM-B2-G01",
    "TG-01": "TG-01-G01",
    "TG-02": "TG-02-G01",
    "TG-03": "TG-03-G01",
    "TG-04": "TG-04-G01",
    "TG-05": "TG-05-G01",
    "TG-06": "TG-06-G01",
    "TG-07": "TG-07-G01",
    "TG-08": "TG-08-G01",
    "TG-09": "TG-09-G01",
    "TG-10": "TG-10-G01",
    "TG-10-LITE": "TG-10-LITE-G01",
}

SUPERSEDED_GENERIC_GATE_ARTIFACTS = {
    "FRM-B1-G01", "FRM-B2-G01", "FRM-B3-G01", "FRM-B4-G01",
    "FRM-B5-G01", "FRM-B6-G01", "FRM-B7-G01",
}


def _explicit_evidence_artifact_code(stage_code, text):
    """Return a form only when the checklist text explicitly identifies it."""
    upper = (text or "").upper()
    for markers, artifact_code in EXPLICIT_EVIDENCE_ARTIFACT_RULES:
        if any(marker in upper for marker in markers):
            return artifact_code
    if stage_code == "TG-06" and "GOLDEN SAMPLE" in upper:
        return "FRM-015"
    if stage_code == "TG-09" and "FINAL SIGN-OFF" in upper:
        return "FRM-022"
    if stage_code in ("TG-10", "TG-10-LITE"):
        return STAGE_MASTER_GATE_ARTIFACTS[stage_code]
    return False


def _checklist_evidence_artifact_code(stage_code, text):
    """Use a named evidence form first, otherwise the source-backed stage gate form."""
    return (
        _explicit_evidence_artifact_code(stage_code, text)
        or STAGE_MASTER_GATE_ARTIFACTS.get(stage_code)
    )


def _subhead(text):
    upper = text.upper()
    if any(word in upper for word in ("CM-", "PAYMENT", "COMMERCIAL", "DUTY", "GST", "PROFITABILITY")):
        return "commercial"
    if "RISK REGISTER" in upper or "PMO" in upper or "PROJECT MARKED" in upper:
        return "governance"
    if "CUSTOMER" in upper:
        return "customer"
    if any(word in upper for word in ("SUPPLIER", "TOOLMAKER", "SHIPPING")):
        return "supplier"
    if any(word in upper for word in ("REPORT", "SUMMARY", "SNAPSHOT", "ARCHIVED")):
        return "reporting"
    return "technical"


def _is_conditional(text):
    upper = text.upper()
    return any(marker in upper for marker in (
        "CONDITIONAL", "WHERE APPLICABLE", "IF IN SCOPE", "OPTION B ONLY",
        "CASE-TO-CASE EXCEPTION", "IF THE TOOLMAKER", "OR FORMALLY WAIVED",
    ))


def _sign_required(text):
    upper = text.upper()
    return any(marker in upper for marker in (
        "SIGNED", "SIGN-OFF", "SIGN OFF", "WRITTEN APPROVAL", "ACKNOWLEDGEMENT",
    ))


class HjigProgrammeTemplateVersion(models.Model):
    _inherit = "hjig.programme.template.version"

    def _sync_authoritative_gate_checklists(self):
        Checklist = self.env["hjig.programme.template.checklist.item"]
        Designation = self.env["hjig.governance.designation"]
        Artifact = self.env["hjig.governance.artifact.master"]
        designation_by_code = {item.code: item for item in Designation.search([])}
        artifact_by_code = {item.code: item for item in Artifact.search([])}
        rows_by_stage = {}
        for stage_code, row_number, text in GATE_FORM_EXIT_ITEMS:
            rows_by_stage.setdefault(stage_code, []).append((row_number, text))

        for version in self.filtered(lambda item: item.execution_mode == "governed_gates"):
            for gate in version.gate_line_ids:
                stage_code = gate.stage_id.code
                gate_form_code = STAGE_MASTER_GATE_ARTIFACTS.get(stage_code)
                gate_form = artifact_by_code.get(gate_form_code)
                if gate_form:
                    existing_rule = version.artifact_rule_ids.filtered(
                        lambda rule: rule.stage_id == gate.stage_id
                        and rule.artifact_master_id == gate_form
                    )[:1]
                    if not existing_rule:
                        self.env["hjig.programme.template.artifact"].create({
                            "version_id": version.id,
                            "artifact_master_id": gate_form.id,
                            "stage_id": gate.stage_id.id,
                            "mandatory": True,
                        })
                if gate.stage_id.stage_type != "milestone":
                    stale_generic = version.artifact_rule_ids.filtered(
                        lambda rule: rule.stage_id == gate.stage_id
                        and rule.artifact_master_id.code in SUPERSEDED_GENERIC_GATE_ARTIFACTS
                    )
                    if stale_generic:
                        stale_generic.unlink()
            activity_by_master = {}
            for activity in version.activity_line_ids:
                for master_code in (activity.legacy_master_codes or "").split(","):
                    if master_code.strip():
                        activity_by_master.setdefault(master_code.strip().upper(), activity)
            expected_codes = set()
            for gate in version.gate_line_ids:
                stage_code = gate.stage_id.code
                stage_rows = rows_by_stage.get(stage_code, [])
                if stage_code in ("PRE-B2", "LGD-SIGNOFF"):
                    stage_rows = [
                        (index, "Completion and controlled evidence confirmed: %s" % activity.name)
                        for index, activity in enumerate(
                            version.activity_line_ids.filtered(
                                lambda item: item.gate_line_id == gate
                            ).sorted("sequence"), start=1
                        )
                    ]
                if not stage_rows:
                    continue
                owner_code, approver_code = STAGE_DESIGNATIONS[stage_code]
                for row_number, text in stage_rows:
                    code = "GF-%s-%02d" % (stage_code.replace("-", ""), row_number)
                    expected_codes.add(code)
                    match = re.search(r"\b(A-\d+[A-Z]?|B8-\d+)\b", text.upper())
                    activity = activity_by_master.get(match.group(1)) if match else False
                    owner = activity.owner_designation_id if activity else designation_by_code[owner_code]
                    approver = activity.approver_designation_id if activity else designation_by_code[approver_code]
                    if owner == approver:
                        owner = designation_by_code[owner_code]
                        approver = designation_by_code[approver_code]
                    evidence_artifact_code = _checklist_evidence_artifact_code(stage_code, text)
                    artifact = artifact_by_code.get(evidence_artifact_code) if evidence_artifact_code else False
                    if not artifact and activity:
                        artifact = activity.required_artifact_ids.filtered(
                            lambda item: gate.stage_id in item.applicable_stage_ids
                        )[:1]
                    upper = text.upper()
                    execution_basis = (
                        "project"
                        if gate.execution_basis == "project" or any(marker in upper for marker in PROJECT_SCOPE_MARKERS)
                        else "mould"
                    )
                    values = {
                        "version_id": version.id,
                        "gate_line_id": gate.id,
                        "code": code,
                        "sequence": row_number * 10,
                        "subhead": _subhead(text),
                        "item_text": text,
                        "mandatory": True,
                        "conditional": _is_conditional(text),
                        "evidence_required": True,
                        "sign_required": _sign_required(text),
                        "execution_basis": execution_basis,
                        "linked_activity_id": activity.id if activity else False,
                        "evidence_artifact_id": artifact.id if artifact else False,
                        "owner_designation_id": owner.id,
                        "approver_designation_id": approver.id,
                        "source_reference": SOURCE_REFERENCE if stage_code not in ("PRE-B2", "LGD-SIGNOFF") else "Hongyi_BSeries_Constitution_v2_5_v6_11 and reconciled legacy programme activities",
                        "source_version": SOURCE_VERSION if stage_code not in ("PRE-B2", "LGD-SIGNOFF") else "v6.11 / Founder approved 21-Aug-2026 / production snapshot 2026-08-27",
                    }
                    item = version.checklist_item_ids.filtered(lambda record: record.code == code)[:1]
                    if item:
                        item.write(values)
                    else:
                        Checklist.create(values)
            stale = version.checklist_item_ids.filtered(
                lambda item: item.code.startswith("GF-") and item.code not in expected_codes
            )
            if stale:
                stale.unlink()
            untyped = version.checklist_item_ids.filtered(
                lambda item: item.evidence_required and not item.evidence_artifact_id
            )
            for item in untyped:
                fallback_code = STAGE_MASTER_GATE_ARTIFACTS.get(item.gate_line_id.stage_id.code)
                fallback = artifact_by_code.get(fallback_code) if fallback_code else False
                if fallback and item.gate_line_id.stage_id in fallback.applicable_stage_ids:
                    item.evidence_artifact_id = fallback.id
        return True
