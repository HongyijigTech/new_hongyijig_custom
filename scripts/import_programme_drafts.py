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


if env.cr.dbname != "HongyijigTech_10Feb":
    raise RuntimeError("Draft import is permitted only in HongyijigTech_10Feb staging")

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
DependencyRule = env["hjig.programme.template.dependency.rule"]
ChecklistItem = env["hjig.programme.template.checklist.item"]

stage_by_code = {stage.code: stage for stage in Stage.search([])}
designation_by_code = {designation.code: designation for designation in Designation.search([])}
master_by_code = {
    master["code"].upper(): master for master in payload.get("activity_masters", [])
}

MOULD_STAGE_CODES = {"TG-02", "TG-03", "TG-04", "TG-05", "TG-06", "TG-07", "TG-08", "TG-09"}


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


DOCUMENTED_DEPENDENCIES = (
    ("A-006", "A-007"), ("A-007", "A-008"), ("A-008", "A-009"),
    ("A-009", "A-010"), ("A-010", "A-011"),
    ("A-014", "A-015"), ("A-015", "A-016"), ("A-016", "A-017"),
    ("A-018", "A-019"), ("A-019", "A-020"), ("A-019", "A-021"),
    ("A-020", "A-021"), ("A-021", "A-022"),
    ("A-023", "A-025"), ("A-024", "A-025"), ("A-025", "A-032"),
    ("A-032", "A-034"), ("A-032", "A-035"),
    ("A-034", "A-036"), ("A-035", "A-036"),
    ("A-036", "A-037"), ("A-037", "A-038"),
    ("A-038", "A-039"), ("A-038", "A-040"), ("A-038", "A-041"),
    ("A-039", "A-042"), ("A-040", "A-042"), ("A-041", "A-042"),
    ("A-042", "A-043"), ("A-043", "A-044"), ("A-043", "A-045"),
    ("A-044", "A-045"), ("A-045", "A-046"), ("A-046", "A-047"),
    ("A-047", "A-048"), ("A-048", "A-049"),
    ("A-049", "A-050"), ("A-049", "A-051"), ("A-049", "A-052"),
    ("A-050", "A-053"), ("A-051", "A-053"), ("A-052", "A-053"),
    ("A-053", "A-054"), ("A-053", "A-055A"), ("A-054", "A-055"),
    ("A-055A", "A-055B"), ("A-055", "A-056"), ("A-055B", "A-056"),
    ("A-056", "A-057"),
    ("A-057", "A-058"), ("A-057", "A-059"), ("A-057", "A-060"),
    ("A-057", "A-061"), ("A-057", "A-062"), ("A-057", "A-063"),
    ("A-057", "A-066"),
    ("A-058", "A-033"), ("A-059", "A-033"), ("A-060", "A-033"),
    ("A-061", "A-033"), ("A-062", "A-033"), ("A-063", "A-033"),
    ("A-033", "A-064"), ("A-064", "A-065"),
    ("A-067", "A-068"), ("A-068", "A-069"), ("A-069", "A-070"),
    ("A-068", "A-071"), ("A-070", "A-072"), ("A-071", "A-072"),
    ("A-072", "A-073"), ("A-073", "A-074"), ("A-074", "A-075"),
    ("A-075", "A-076"), ("A-076", "A-077"),
    ("A-078", "A-079"), ("A-079", "A-080"),
    ("A-082", "A-083"), ("A-082", "A-084"), ("A-082", "A-085"),
    ("A-085", "A-086"), ("A-086", "A-087"), ("A-087", "A-088"),
    ("A-088", "A-089"), ("A-089", "A-090"), ("A-090", "A-092"),
    ("B8-01", "B8-09"), ("B8-02", "B8-09"), ("B8-03", "B8-09"),
    ("B8-04", "B8-09"), ("B8-05", "B8-09"), ("B8-06", "B8-09"),
    ("B8-07", "B8-09"), ("B8-08", "B8-09"),
)


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

    applicable = [
        rule for rule in payload.get("dependency_rules", [])
        if programme_code in rule.get("applicable_programmes", [])
    ]
    expected_source_ids = set()

    def upsert_rule(source_rule_id, predecessor, successor, values):
        existing = DependencyRule.search([
            ("version_id", "=", version.id),
            ("legacy_source_rule_id", "=", source_rule_id),
        ], limit=1)
        rule_values = {
            "version_id": version.id,
            "legacy_source_rule_id": source_rule_id,
            "predecessor_activity_id": predecessor.id,
            "successor_activity_id": successor.id,
        }
        rule_values.update(values)
        if existing:
            existing.write(rule_values)
        else:
            DependencyRule.create(rule_values)
        if predecessor not in successor.predecessor_ids:
            successor.predecessor_ids = [(4, predecessor.id)]
        expected_source_ids.add(source_rule_id)

    unmapped = []
    for source_rule in applicable:
        predecessor = activity_by_master_code.get(source_rule["predecessor_master_code"].upper())
        successor = activity_by_master_code.get(source_rule["successor_master_code"].upper())
        if not predecessor or not successor:
            unmapped.append(source_rule["id"])
            continue
        upsert_rule(source_rule["id"], predecessor, successor, {
            "predecessor_basis": source_rule["predecessor_basis"],
            "successor_basis": source_rule["successor_basis"],
            "rule_type": source_rule["rule_type"],
            "scope_matching_rule": source_rule["scope_matching_rule"],
            "aggregation_requirement": source_rule["aggregation_requirement"],
            "conditional_handling": source_rule.get("conditional_handling"),
            "source_reference": source_rule.get("source_reference"),
            "source_version": source_rule.get("source_version"),
        })
    if unmapped:
        raise RuntimeError(
            "%s dependency rules do not map to route activities: %s"
            % (programme_code, ",".join(map(str, unmapped)))
        )

    documented_pairs = list(DOCUMENTED_DEPENDENCIES)
    if programme_code == "LGC":
        documented_pairs.extend((
            ("A-011", "A-012"), ("A-011", "A-013"),
            ("A-012", "A-014"), ("A-013", "A-014"),
        ))
    elif programme_code in ("LGV", "TLC"):
        documented_pairs.extend((
            ("A-012", "A-013"), ("A-012", "A-014"), ("A-013", "A-014"),
        ))

    represented_pairs = {
        (rule.predecessor_activity_id.id, rule.successor_activity_id.id)
        for rule in version.dependency_rule_ids.filtered(
            lambda item: item.legacy_source_rule_id in expected_source_ids
        )
    }
    documented_count = 0
    for index, (predecessor_code, successor_code) in enumerate(documented_pairs, start=1):
        predecessor = activity_by_master_code.get(predecessor_code)
        successor = activity_by_master_code.get(successor_code)
        if not predecessor or not successor:
            continue
        if predecessor.sequence >= successor.sequence:
            raise RuntimeError(
                "%s documented dependency is not forward-only: %s -> %s"
                % (programme_code, predecessor_code, successor_code)
            )
        if (predecessor.id, successor.id) in represented_pairs:
            continue
        source_rule_id = -100000 - index
        upsert_rule(source_rule_id, predecessor, successor, {
            "predecessor_basis": predecessor.execution_basis,
            "successor_basis": successor.execution_basis,
            "rule_type": "documented_sequence",
            "scope_matching_rule": "%s->%s (authoritative B-Series sequence)" % (
                predecessor.execution_basis.upper(), successor.execution_basis.upper()
            ),
            "aggregation_requirement": "Complete the documented predecessor before starting the successor.",
            "conditional_handling": "Conditional predecessors require an approved N/A disposition when out of scope.",
            "source_reference": "Hongyi_BSeries_Activity_Dependencies_v1_2",
            "source_version": "v1.2 / Drive revision AIroW34bcutBBn3i2KyIeSGTKVX3V5h3UHJ9n8i8kRG0yU98hEUj4Dt0qyUGAx6FprWFIlQQFCSsbQbauMO_KZzuIY0nHHnrn3sfEA_X1xA",
        })
        represented_pairs.add((predecessor.id, successor.id))
        documented_count += 1

    # CM milestones are not Activity Master records, so bind the two explicit
    # payment blocks by their governed task labels.
    cm05 = version.activity_line_ids.filtered(lambda item: (item.name or "").upper().startswith("CM-05:"))[:1]
    trial_t0 = activity_by_master_code.get("A-036")
    if cm05 and trial_t0 and (cm05.id, trial_t0.id) not in represented_pairs:
        upsert_rule(-100500, cm05, trial_t0, {
            "predecessor_basis": "project", "successor_basis": trial_t0.execution_basis,
            "rule_type": "commercial_hard_block",
            "scope_matching_rule": "PROJECT->MOULD (same programme run)",
            "aggregation_requirement": "CM-05 must be confirmed before T0 trial.",
            "conditional_handling": "Not conditional.",
            "source_reference": "Hongyi_BSeries_Activity_Dependencies_v1_2 Table 10",
            "source_version": "v1.2",
        })
        represented_pairs.add((cm05.id, trial_t0.id))
        documented_count += 1

    cm08 = version.activity_line_ids.filtered(lambda item: (item.name or "").upper().startswith("CM-08:"))[:1]
    payment_verified = activity_by_master_code.get("A-081")
    cm09 = version.activity_line_ids.filtered(lambda item: (item.name or "").upper().startswith("CM-09:"))[:1]
    delivery = activity_by_master_code.get("A-082")
    for source_rule_id, predecessor, successor, requirement in (
        (-100501, cm08, payment_verified, "Customer duty demand must precede payment verification."),
        (-100502, payment_verified, cm09, "Customer payment must be verified before HJIG pays agencies."),
        (-100503, cm09, delivery, "Agency payment and BOE filing must precede customs clearance and delivery."),
    ):
        if predecessor and successor and (predecessor.id, successor.id) not in represented_pairs:
            upsert_rule(source_rule_id, predecessor, successor, {
                "predecessor_basis": "project", "successor_basis": successor.execution_basis,
                "rule_type": "commercial_hard_block",
                "scope_matching_rule": "PROJECT->PROJECT (same programme run)",
                "aggregation_requirement": requirement,
                "conditional_handling": "Not conditional.",
                "source_reference": "Hongyi_BSeries_Activity_Dependencies_v1_2 Table 15",
                "source_version": "v1.2",
            })
            represented_pairs.add((predecessor.id, successor.id))
            documented_count += 1
    # Gate barriers are derived from the verified route itself. Every activity in a
    # later gate waits for every activity in the immediately preceding gate, while
    # the 34 source rules retain the component/mould aggregation semantics inside gates.
    barrier_source_id = -1
    ordered_gates = version.gate_line_ids.filtered("required").sorted("sequence")
    for previous_gate, current_gate in zip(ordered_gates, ordered_gates[1:]):
        predecessors = version.activity_line_ids.filtered(
            lambda activity: activity.gate_line_id == previous_gate
        ).sorted("sequence")
        successors = version.activity_line_ids.filtered(
            lambda activity: activity.gate_line_id == current_gate
        ).sorted("sequence")
        for predecessor in predecessors:
            for successor in successors:
                upsert_rule(barrier_source_id, predecessor, successor, {
                    "predecessor_basis": "project",
                    "successor_basis": "project",
                    "rule_type": "gate_barrier",
                    "scope_matching_rule": "PROJECT->PROJECT (same programme run)",
                    "aggregation_requirement": "All activities in the immediately preceding gate must complete.",
                    "conditional_handling": "Gate barrier; conditional activities require approved disposition.",
                    "source_reference": "Verified legacy programme stage route",
                    "source_version": payload.get("snapshot_sha256") or "snapshot",
                })
                barrier_source_id -= 1
    stale = version.dependency_rule_ids.filtered(
        lambda rule: rule.legacy_source_rule_id not in expected_source_ids
    )
    if stale:
        stale.unlink()
    if len(version.dependency_rule_ids) != len(expected_source_ids):
        raise RuntimeError("%s dependency rule count does not reconcile" % programme_code)
    return len(applicable), documented_count, len(expected_source_ids) - len(applicable) - documented_count

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
            "duration_days": 1,
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
