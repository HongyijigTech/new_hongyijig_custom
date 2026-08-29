"""Run with Odoo shell against staging to create unapproved draft DNA."""

import json
import os
import re


INPUT_PATH = os.environ.get(
    "HJIG_PROGRAMME_SNAPSHOT_PATH", "/tmp/hjig_programme_legacy_snapshot.json"
)
PROGRAMMES = {
    1: ("LGC", 141),
    2: ("LGD", 22),
    3: ("LGV", 127),
    4: ("TLC", 106),
    5: ("TLL", 12),
}


def canonical_stage(stage_name):
    upper = (stage_name or "").upper()
    if "SESSION" in upper:
        match = re.search(r"SESSION\s*(\d+)", upper)
        if match:
            return "TLL-S%02d" % int(match.group(1))
    if "PRE-B2" in upper:
        return "PRE-B2"
    if "TG-10-LITE" in upper:
        return "TG-10-LITE"
    match = re.search(r"TG-(\d{2})", upper)
    if match:
        return "TG-%s" % match.group(1)
    if "IG-01" in upper or "PROJECT PLANNING" in upper:
        return "PA-00"
    if "DESIGN ONLY" in upper:
        return "LGD-SIGNOFF"
    raise RuntimeError("No canonical gate mapping for legacy stage: %s" % stage_name)


def designations_for(stage_code, activity_name):
    upper = (activity_name or "").upper()
    if stage_code == "PA-00":
        return "PROJECT-COORD", "PROJECT-MANAGER"
    if stage_code in ("TG-01", "LGD-SIGNOFF"):
        if any(word in upper for word in ("TOOLMAKER", "COMMERCIAL", "SUPPLIER")):
            return "PROJECT-MANAGER", "PMO-DOC"
        return "SR-PRODUCT-DESIGN", "PROJECT-MANAGER"
    if stage_code == "PRE-B2":
        return "PROJECT-MANAGER", "PMO-DOC"
    if stage_code == "TG-02":
        return "SR-TOOL-DESIGN", "PROJECT-MANAGER"
    if stage_code == "TG-03":
        return "SR-TOOL-DEVELOPMENT", "PROJECT-MANAGER"
    if stage_code in ("TG-04", "TG-05", "TG-06"):
        if any(word in upper for word in ("INSPECTION", "DIMENSION", "VISUAL", "ASSEMBLY", "QUALITY")):
            return "QUALITY-INSPECTION", "PROJECT-MANAGER"
        return "PROJECT-ENGINEER", "PROJECT-MANAGER"
    if stage_code in ("TG-07", "TG-08"):
        return "COMMERCIAL-LOGISTICS", "PROJECT-MANAGER"
    if stage_code == "TG-09":
        return "PROJECT-ENGINEER", "CUSTOMER-APPROVER"
    if stage_code in ("TG-10", "TG-10-LITE"):
        return "PROJECT-MANAGER", "PMO-DOC"
    if stage_code.startswith("TLL-S"):
        return "PROJECT-ENGINEER", "PROJECT-MANAGER"
    raise RuntimeError("No designation rule for canonical stage %s" % stage_code)


database_name = env.cr.dbname
explicit_database = os.environ.get("HJIG_PROGRAMME_IMPORT_DB")
explicit_target_allowed = explicit_database == database_name and (
    database_name == "hongyijig_30April_db"
    or database_name.startswith("hongyijig_bseries_v127_test_")
)
if database_name != "HongyijigTech_10Feb" and not explicit_target_allowed:
    raise RuntimeError(
        "Draft import requires staging or an exact HJIG_PROGRAMME_IMPORT_DB production/test target"
    )

with open(INPUT_PATH, "r", encoding="utf-8") as snapshot:
    payload = json.load(snapshot)
if payload.get("source_database") != "hongyijig_30April_db":
    raise RuntimeError("Snapshot source database is not the verified production database")

Stage = env["hjig.launchguard.stage"]
Designation = env["hjig.governance.designation"]
Version = env["hjig.programme.template.version"]
Gate = env["hjig.programme.template.gate"]
Activity = env["hjig.programme.template.activity"]
ArtifactRule = env["hjig.programme.template.artifact"]
Artifact = env["hjig.governance.artifact.master"]
ChecklistItem = env["hjig.programme.template.checklist.item"]
AdvisorySession = env["hjig.programme.template.session"]

stage_by_code = {stage.code: stage for stage in Stage.search([])}
designation_by_code = {designation.code: designation for designation in Designation.search([])}
master_by_code = {
    master["code"].upper(): master for master in payload.get("activity_masters", [])
}

MOULD_STAGE_CODES = {"TG-02", "TG-03", "TG-04", "TG-05", "TG-06", "TG-07", "TG-08", "TG-09"}

TLL_SESSIONS = (
    ("TLL-S01", 10, "SOR + BOP Collection Advisory", "1 full day", "FRM-TLL-001"),
    ("TLL-S02", 20, "RFQ Framework Advisory", "Half day", "FRM-TLL-002"),
    ("TLL-S03", 30, "Supplier Selection Methodology Advisory", "Half day", "FRM-TLL-003"),
    ("TLL-S04", 40, "Pre-Tooling Governance Advisory", "Half day", "FRM-TLL-004"),
    ("TLL-S05", 50, "Trial Sign-Off Advisory", "Half day", "FRM-TLL-005"),
    ("TLL-S06", 60, "Dispatch Readiness Advisory", "Half day", "FRM-TLL-006"),
)


def gate_basis(stage_code):
    return "mould" if stage_code in MOULD_STAGE_CODES else "project"


def sync_artifact_rules(version):
    valid_stage_ids = set(version.gate_line_ids.mapped("stage_id").ids)
    stale = version.artifact_rule_ids.filtered(
        lambda rule: rule.stage_id.id not in valid_stage_ids
    )
    if stale:
        stale.unlink()
    existing = {
        (rule.stage_id.id, rule.artifact_master_id.id)
        for rule in version.artifact_rule_ids
    }
    for gate in version.gate_line_ids:
        artifacts = Artifact.search([("applicable_stage_ids", "in", gate.stage_id.id)])
        for artifact in artifacts:
            key = (gate.stage_id.id, artifact.id)
            if key not in existing:
                ArtifactRule.create({
                    "version_id": version.id,
                    "artifact_master_id": artifact.id,
                    "stage_id": gate.stage_id.id,
                    "mandatory": True,
                })
                existing.add(key)


def sync_route_gates(version, tasks):
    """Reconcile draft gate identity to the authoritative programme route."""
    ordered_stage_codes = []
    for task in tasks:
        code = canonical_stage(task["stage_name"])
        if code not in ordered_stage_codes:
            ordered_stage_codes.append(code)
    existing = version.gate_line_ids.sorted("sequence")
    if len(existing) != len(ordered_stage_codes):
        raise RuntimeError(
            "%s gate count does not reconcile to the authoritative route"
            % version.template_id.code
        )
    gate_by_code = {}
    for sequence, (gate, code) in enumerate(zip(existing, ordered_stage_codes), start=1):
        stage = stage_by_code.get(code)
        if not stage:
            raise RuntimeError("Missing canonical staging gate %s" % code)
        gate.write({
            "stage_id": stage.id,
            "sequence": sequence * 10,
            "closure_variant": "lite" if code == "TG-10-LITE" else "standard",
            "execution_basis": gate_basis(code),
        })
        gate_by_code[code] = gate
    for activity in version.activity_line_ids:
        source = next(task for task in tasks if task["id"] == activity.legacy_source_task_id)
        gate = gate_by_code[canonical_stage(source["stage_name"])]
        if activity.gate_line_id != gate:
            activity.gate_line_id = gate
    return gate_by_code


IG01_CHECKLIST_ITEMS = (
    ("IG01-G01", "governance", "Project Code assigned; Primary Senior Tool Design Engineer and Project Coordinator / Junior PM designations assigned.", True, False, True, False, None, "PROJECT-COORD", "PROJECT-MANAGER", None, 0, ("LGC", "LGD", "LGV", "TLC")),
    ("IG01-G02", "governance", "Risk Register received from P-Series and deepened.", True, False, True, False, "A-005", "PROJECT-ENGINEER", "PROJECT-MANAGER", "FRM-006", 0, ("LGC", "LGD", "LGV", "TLC")),
    ("IG01-G03", "governance", "Risk Score 16 or higher has triggered PMO escalation with controlled evidence.", True, True, True, False, "A-005", "PMO-DOC", "FOUNDER-MD", "FRM-006", 16, ("LGC", "LGD", "LGV", "TLC")),
    ("IG01-G04", "governance", "Project Plan built using the standard activity template and governed standard days.", True, False, True, False, None, "PROJECT-MANAGER", "PMO-DOC", None, 0, ("LGC", "LGD", "LGV", "TLC")),
    ("IG01-G05", "governance", "Risk Score 12 or higher has triggered mitigation activities in the Project Plan.", True, True, True, False, "A-005", "PROJECT-MANAGER", "PMO-DOC", "FRM-006", 12, ("LGC", "LGD", "LGV", "TLC")),
    ("IG01-G06", "governance", "Customer-specific supplementary tasks are added and traced to the Risk Register or customer request.", False, False, True, False, None, "PROJECT-MANAGER", "PMO-DOC", None, 0, ("LGC", "LGD", "LGV", "TLC")),
    ("IG01-G07", "governance", "Founder / Managing Director designation approval received on the Project Plan before gate close.", True, False, True, True, None, "PROJECT-MANAGER", "FOUNDER-MD", None, 0, ("LGC", "LGD", "LGV", "TLC")),
    ("IG01-G08", "governance", "The applicable B-Series programme is confirmed.", True, False, True, False, None, "PROJECT-MANAGER", "PMO-DOC", None, 0, ("LGC", "LGD", "LGV", "TLC")),
    ("IG01-G09", "governance", "Risk Register final review confirms no unresolved new risk with score 16 or higher.", True, False, True, False, "A-005", "PROJECT-MANAGER", "PMO-DOC", "FRM-006", 0, ("LGC", "LGD", "LGV", "TLC")),
    ("IG01-T01", "technical", "SOR is complete, 100 percent project-basis, and signed by the customer.", True, False, True, True, "A-001", "PROJECT-ENGINEER", "PROJECT-MANAGER", "FRM-003", 0, ("LGC", "LGD", "LGV", "TLC")),
    ("IG01-T02", "technical", "BOP is complete, frozen for all components, and signed.", True, False, True, True, "A-002", "PROJECT-ENGINEER", "PROJECT-MANAGER", "FRM-004", 0, ("LGC", "LGD", "LGV", "TLC")),
    ("IG01-T03", "technical", "Product design and manufacturing challenges are documented in the customer's exact words.", True, False, True, False, "A-003", "PROJECT-ENGINEER", "PROJECT-MANAGER", None, 0, ("LGC", "LGD", "LGV", "TLC")),
    ("IG01-T04", "technical", "Tentative Mould Planning is complete; the mould list will lock at the applicable design/pre-B2 gate.", True, False, True, False, "A-004", "SR-TOOL-DESIGN", "PROJECT-MANAGER", "FRM-005", 0, ("LGC", "LGD", "LGV", "TLC")),
    ("IG01-T05", "technical", "BOP physical samples are received by HJIG and verified against SOR and assembly.", True, False, True, False, None, "PROJECT-ENGINEER", "PROJECT-MANAGER", None, 0, ("LGC", "LGD", "LGV", "TLC")),
    ("IG01-T06", "technical", "Styling or A-Class surface data is available, or a benchmark sample is received.", False, False, True, False, None, "SR-PRODUCT-DESIGN", "PROJECT-MANAGER", None, 0, ("LGC", "LGD")),
    ("IG01-R01", "reporting", "Estimated project timeline based on the final SOR is shared with the customer.", True, False, True, False, None, "PROJECT-MANAGER", "PMO-DOC", None, 0, ("LGC", "LGD", "LGV", "TLC")),
    ("IG01-CU01", "customer", "Design agency is identified for the programme's product-design scope.", True, False, True, False, None, "SR-PRODUCT-DESIGN", "PROJECT-MANAGER", None, 0, ("LGC", "LGD")),
    ("IG01-S01", "supplier", "Existing customer SOR, BOP, Design Challenges and Mould Planning records are reviewed, updated and signed off by HJIG before pre-B2 entry.", True, False, True, True, None, "PROJECT-MANAGER", "PMO-DOC", None, 0, ("LGV", "TLC")),
)


def sync_ig01_checklist(version):
    programme_code = version.template_id.code
    gate = version.gate_line_ids.filtered(lambda item: item.stage_id.code == "PA-00")[:1]
    if not gate:
        return 0
    activity_by_master = {}
    for activity in version.activity_line_ids:
        for code in (activity.legacy_master_codes or "").split(","):
            if code.strip():
                activity_by_master[code.strip().upper()] = activity
    artifact_by_code = {item.code: item for item in Artifact.search([])}
    expected = set()
    for sequence, values in enumerate(IG01_CHECKLIST_ITEMS, start=1):
        (code, subhead, text, mandatory, conditional, evidence_required, sign_required,
         linked_code, owner_code, approver_code, artifact_code, threshold, programmes) = values
        if programme_code not in programmes:
            continue
        expected.add(code)
        vals = {
            "version_id": version.id,
            "gate_line_id": gate.id,
            "code": code,
            "sequence": sequence * 10,
            "subhead": subhead,
            "item_text": text,
            "mandatory": mandatory,
            "conditional": conditional,
            "evidence_required": evidence_required,
            "sign_required": sign_required,
            "execution_basis": "project",
            "linked_activity_id": activity_by_master.get(linked_code).id if linked_code and activity_by_master.get(linked_code) else False,
            "evidence_artifact_id": artifact_by_code.get(artifact_code).id if artifact_code and artifact_by_code.get(artifact_code) else False,
            "owner_designation_id": designation_by_code[owner_code].id,
            "approver_designation_id": designation_by_code[approver_code].id,
            "auto_na_risk_below": threshold,
            "source_reference": "BSeries_Checklist_Template_Model_Spec_v2 Section 9",
            "source_version": "v2 / July 2026",
        }
        item = version.checklist_item_ids.filtered(lambda record: record.code == code)[:1]
        if item:
            item.write(vals)
        else:
            ChecklistItem.create(vals)
    stale = version.checklist_item_ids.filtered(
        lambda item: item.gate_line_id == gate and item.code.startswith("IG01-") and item.code not in expected
    )
    if stale:
        stale.unlink()
    return len(expected)


ACTIVITY_ARTIFACTS = {
    "A-001": ("FRM-003",),
    "A-002": ("FRM-004",),
    "A-004": ("FRM-005",),
    "A-005": ("FRM-006",),
    "A-006": ("FRM-027",), "A-007": ("FRM-027",),
    "A-008": ("FRM-027",), "A-009": ("FRM-027",),
    "A-010": ("FRM-027",), "A-011": ("FRM-027",),
    "A-012": ("FRM-007",), "A-013": ("FRM-003",),
    "A-014": ("FRM-028", "FRM-029"), "A-015": ("FRM-028", "FRM-029"),
    "A-016": ("FRM-028", "FRM-029"), "A-017": ("FRM-028", "FRM-029"),
    "A-019": ("FRM-030",), "A-020": ("FRM-031",),
    "A-021": ("FRM-032",), "A-022": ("FRM-033",),
    "A-023": ("FRM-034",), "A-024": ("FRM-034",), "A-025": ("FRM-034",),
    "A-026": ("FRM-034",), "A-031": ("FRM-034",), "A-032": ("FRM-034",),
    "A-034": ("FRM-034",), "A-035": ("FRM-034",), "A-036": ("FRM-034",),
    "A-039": ("FRM-011",), "A-040": ("FRM-012",), "A-041": ("FRM-013",),
    "A-042": ("FRM-014",), "A-043": ("FRM-035",), "A-044": ("FRM-010",),
    "A-045": ("FRM-036",), "A-046": ("FRM-036",), "A-047": ("FRM-014",),
    "A-050": ("FRM-011",), "A-051": ("FRM-012",), "A-052": ("FRM-013",),
    "A-053": ("FRM-035",), "A-054": ("FRM-036",), "A-055": ("FRM-036",),
    "A-055A": ("FRM-035",), "A-055B": ("FRM-035",), "A-056": ("FRM-014",),
    "A-057": ("FRM-015",), "A-058": ("FRM-037",),
    "A-061": ("FRM-011",), "A-062": ("FRM-012",), "A-063": ("FRM-013",),
    "A-067": ("FRM-016",), "A-068": ("FRM-038",),
    "A-069": ("FRM-017",), "A-070": ("FRM-017",),
    "A-071": ("FRM-017",), "A-072": ("FRM-017", "FRM-039"),
    "A-073": ("FRM-040",), "A-074": ("FRM-040",), "A-075": ("FRM-040",),
    "A-076": ("FRM-018",), "A-077": ("FRM-018",), "A-078": ("FRM-041",),
    "A-079": ("FRM-041",), "A-080": ("FRM-041",), "A-081": ("FRM-041",),
    "A-082": ("FRM-019", "FRM-041"), "A-083": ("FRM-019",), "A-084": ("FRM-041",),
    "A-085": ("FRM-020",), "A-086": ("FRM-021",), "A-087": ("FRM-042",),
    "A-088": ("FRM-042",), "A-089": ("FRM-022",), "A-090": ("FRM-022",),
    "B8-01": ("FRM-043",), "B8-02": ("FRM-043",), "B8-03": ("FRM-043",),
    "B8-04": ("FRM-043",), "B8-05": ("FRM-043",), "B8-06": ("FRM-023", "FRM-043"),
    "B8-07": ("FRM-043",), "B8-08": ("FRM-043",), "B8-09": ("FRM-043",),
}


def sync_activity_artifacts(version):
    artifact_by_code = {item.code.upper(): item for item in Artifact.search([])}
    permitted = {
        (rule.stage_id.id, rule.artifact_master_id.id)
        for rule in version.artifact_rule_ids
    }
    for activity in version.activity_line_ids:
        codes = [code.strip().upper() for code in (activity.legacy_master_codes or "").split(",") if code.strip()]
        required_codes = set()
        for code in codes:
            required_codes.update(ACTIVITY_ARTIFACTS.get(code, ()))
        upper_name = (activity.name or "").upper()
        if "RISK REGISTER" in upper_name:
            required_codes.add("FRM-006")
        if activity.gate_line_id.stage_id.code.startswith("TLL-S"):
            required_codes.add(
                "FRM-TLL-%03d" % int(activity.gate_line_id.stage_id.code[-2:])
            )
        artifacts = Artifact.browse()
        for code in sorted(required_codes):
            artifact = artifact_by_code.get(code)
            if artifact and (activity.gate_line_id.stage_id.id, artifact.id) in permitted:
                artifacts |= artifact
        activity.required_artifact_ids = [(6, 0, artifacts.ids)]


def sync_dependency_rules(version, programme_code, task_payload_by_id):
    activity_by_master_code = {}
    for activity in version.activity_line_ids:
        source = task_payload_by_id[activity.legacy_source_task_id]
        codes = [code.upper() for code in source.get("activity_master_codes", [])]
        values = {"legacy_master_codes": ",".join(codes) or False}
        if codes:
            master = master_by_code.get(codes[0], {})
            values.update({
                "execution_basis": master.get("basis") or "project",
                "conditional": bool(master.get("conditional")),
            })
        activity.write(values)
        for code in codes:
            if code in activity_by_master_code and activity_by_master_code[code] != activity:
                raise RuntimeError("Duplicate Activity Master code %s in %s" % (code, programme_code))
            activity_by_master_code[code] = activity

    # The production snapshot may contain superseded v1.2 dependency evidence.
    # Execution authority is rebuilt only from Founder-approved v1.4.
    version._sync_founder_approved_dependency_rules()
    return len(version.dependency_rule_ids), len(version.dependency_rule_ids), 0

for project_id, (programme_code, expected_count) in PROGRAMMES.items():
    tasks = payload["projects"].get(str(project_id), [])
    task_payload_by_id = {task["id"]: task for task in tasks}
    if len(tasks) != expected_count:
        raise RuntimeError("Snapshot count mismatch for Project %s" % project_id)
    template = env["hjig.programme.template"].search([("code", "=", programme_code)], limit=1)
    if not template:
        raise RuntimeError("Missing programme template %s" % programme_code)
    version = Version.search(
        [("template_id", "=", template.id), ("version", "=", "1.0")], limit=1
    )
    if programme_code == "TLL":
        template.write({
            "execution_mode": "advisory_sessions",
            "description": "Six-session advisory programme; no B-Series gates or execution monitoring. Legacy source: Project 5.",
        })
        values = {
            "legacy_source_database": payload["source_database"],
            "legacy_source_project_id": project_id,
            "legacy_source_task_count": expected_count,
            "dependency_review_status": "unreviewed",
            "evidence_review_status": "unreviewed",
            "timing_review_status": "unreviewed",
        }
        if not version:
            values.update({"template_id": template.id, "version": "1.0"})
            version = Version.create(values)
        else:
            version.write(values)
        if version.gate_line_ids:
            version.dependency_rule_ids.unlink()
            version.checklist_item_ids.unlink()
            version.artifact_rule_ids.unlink()
            version.activity_line_ids.unlink()
            version.gate_line_ids.unlink()
        grouped = {}
        for task in tasks:
            grouped.setdefault(canonical_stage(task["stage_name"]), []).append(task["id"])
        expected_ids = {task["id"] for task in tasks}
        existing_ids = {
            int(source_id)
            for session in version.session_line_ids
            for source_id in (session.legacy_source_task_ids or "").split(",")
            if source_id
        }
        if version.session_line_ids and existing_ids != expected_ids:
            raise RuntimeError("Existing TLL v1.0 sessions do not reconcile to source")
        for code, sequence, name, duration, artifact_code in TLL_SESSIONS:
            source_ids = grouped.get(code, [])
            if len(source_ids) != 2:
                raise RuntimeError("%s must reconcile exactly two legacy task references" % code)
            artifact = Artifact.search([("code", "=", artifact_code)], limit=1)
            stage = Stage.search([("code", "=", code)], limit=1)
            if not artifact:
                raise RuntimeError("Missing governed ToolLock Lite framework %s" % artifact_code)
            if not stage:
                raise RuntimeError("Missing governed ToolLock Lite stage %s" % code)
            values = {
                "version_id": version.id,
                "code": code,
                "sequence": sequence,
                "name": name,
                "indicative_duration": duration,
                "stage_id": stage.id,
                "owner_designation_id": artifact.owner_designation_id.id,
                "approver_designation_id": artifact.approver_designation_id.id,
                "framework_artifact_id": artifact.id,
                "legacy_source_task_ids": ",".join(map(str, source_ids)),
                "source_task_count": len(source_ids),
                "source_reference": "Hongyi_BSeries_Constitution_v2_5_v6_9",
                "source_version": "v6.9",
                "advisory_scope": "Advisory review using a blank controlled framework; tooling execution monitoring and filled proprietary templates are outside scope.",
            }
            session = version.session_line_ids.filtered(lambda item: item.code == code)[:1]
            if session:
                session.write(values)
            else:
                AdvisorySession.create(values)
        print(
            "PROGRAMME_RECONCILED", programme_code, "ADVISORY_SESSIONS",
            len(version.session_line_ids), "LEGACY_REFERENCES", len(expected_ids), version.state,
        )
        continue
    if version and version.activity_line_ids:
        source_ids = set(version.activity_line_ids.mapped("legacy_source_task_id"))
        expected_ids = {task["id"] for task in tasks}
        if source_ids != expected_ids:
            raise RuntimeError("Existing %s v1.0 draft does not reconcile to source" % programme_code)
        sync_route_gates(version, tasks)
        sync_artifact_rules(version)
        sync_activity_artifacts(version)
        dependency_count, documented_count, barrier_count = sync_dependency_rules(
            version, programme_code, task_payload_by_id
        )
        checklist_count = sync_ig01_checklist(version)
        version._sync_authoritative_gate_checklists()
        checklist_count = len(version.checklist_item_ids)
        print(
            "PROGRAMME_ALREADY_RECONCILED",
            programme_code,
            len(source_ids),
            len(version.artifact_rule_ids),
            dependency_count,
            documented_count,
            barrier_count,
            checklist_count,
        )
        continue
    values = {
        "legacy_source_database": payload["source_database"],
        "legacy_source_project_id": project_id,
        "legacy_source_task_count": expected_count,
        # These stay unreviewed until the business-approved dependency and evidence
        # maps have been reconciled. Draft import must never self-approve governance.
        "dependency_review_status": "unreviewed",
        "evidence_review_status": "unreviewed",
        "timing_review_status": "unreviewed",
    }
    if not version:
        values.update({"template_id": template.id, "version": "1.0"})
        version = Version.create(values)
    else:
        version.write(values)

    gate_by_code = {}
    ordered_stage_codes = []
    for task in tasks:
        code = canonical_stage(task["stage_name"])
        if code not in ordered_stage_codes:
            ordered_stage_codes.append(code)
    for sequence, code in enumerate(ordered_stage_codes, start=1):
        stage = stage_by_code.get(code)
        if not stage:
            raise RuntimeError("Missing canonical staging gate %s" % code)
        gate_by_code[code] = Gate.create({
            "version_id": version.id,
            "stage_id": stage.id,
            "sequence": sequence * 10,
            "closure_variant": "lite" if code == "TG-10-LITE" else "standard",
            "execution_basis": gate_basis(code),
        })

    for index, task in enumerate(tasks, start=1):
        stage_code = canonical_stage(task["stage_name"])
        owner_code, approver_code = designations_for(stage_code, task["name"])
        owner = designation_by_code.get(owner_code)
        approver = designation_by_code.get(approver_code)
        if not owner or not approver:
            raise RuntimeError("Missing designation %s/%s" % (owner_code, approver_code))
        Activity.create({
            "version_id": version.id,
            "code": "%s-A%03d" % (programme_code, index),
            "name": task["name"],
            "sequence": index * 10,
            "gate_line_id": gate_by_code[stage_code].id,
            "owner_designation_id": owner.id,
            "approver_designation_id": approver.id,
            "duration_days": 0,
            "legacy_source_task_id": task["id"],
            "legacy_source_stage_id": task["stage_id"],
            "legacy_source_stage_name": task["stage_name"],
            "legacy_master_codes": ",".join(task.get("activity_master_codes", [])) or False,
        })

    sync_artifact_rules(version)
    sync_activity_artifacts(version)
    dependency_count, documented_count, barrier_count = sync_dependency_rules(
        version, programme_code, task_payload_by_id
    )
    checklist_count = sync_ig01_checklist(version)
    version._sync_authoritative_gate_checklists()
    checklist_count = len(version.checklist_item_ids)
    print(
        "PROGRAMME_RECONCILED",
        programme_code,
        len(version.gate_line_ids),
        len(version.activity_line_ids),
        len(version.artifact_rule_ids),
        dependency_count,
        documented_count,
        barrier_count,
        checklist_count,
        version.state,
    )

env.cr.commit()
print("DRAFT_IMPORT_COMPLETE_COMMITTED")
