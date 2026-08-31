import json
import math

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


LIFECYCLE_STAGES = [
    ("ig01", "IG-01 - Tentative Mould Plan"),
    ("tg01", "TG-01 - Mould Architecture Lock"),
    ("tg02", "TG-02 - Engineering Mould Definition"),
    ("tg03", "TG-03 - Tooling Release / Frozen Plan"),
    ("closure", "Closure - As-Built Mould Record"),
]
STAGE_ORDER = {code: index for index, (code, _label) in enumerate(LIFECYCLE_STAGES)}


class HjigMouldLifecycle(models.Model):
    _inherit = "x_mould"

    x_mould_image = fields.Image(string="Mould / Concept Image", attachment=True, tracking=True)
    x_lifecycle_stage = fields.Selection(LIFECYCLE_STAGES, default="ig01", required=True, tracking=True)
    x_special_technology = fields.Selection([
        ("none", "None"), ("two_k", "2K / Multi-material"), ("insert", "Insert Moulding"),
        ("overmould", "Overmoulding"), ("stack", "Stack Mould"), ("other", "Other"), ("tbd", "TBD"),
    ], default="none", required=True, tracking=True)
    x_planning_confidence = fields.Selection(
        [("high", "High"), ("medium", "Medium"), ("low", "Low")], default="medium", required=True, tracking=True
    )
    x_grouping_basis = fields.Text(tracking=True)
    x_planning_assumption = fields.Text(tracking=True)
    x_open_technical_question = fields.Text(tracking=True)
    x_customer_input_pending = fields.Text(tracking=True)
    x_engineering_input_pending = fields.Text(tracking=True)
    x_risk_flag = fields.Boolean(tracking=True)
    x_risk_note = fields.Text(tracking=True)
    x_cavity_engineering_justification = fields.Text(tracking=True)
    x_cavitation_confirmed = fields.Boolean(tracking=True)

    x_mould_length_mm = fields.Float(tracking=True)
    x_mould_width_mm = fields.Float(tracking=True)
    x_mould_height_mm = fields.Float(string="Mould Height / Stack (mm)", tracking=True)
    x_estimated_weight_kg = fields.Float(tracking=True)
    x_target_tool_life = fields.Selection([
        ("100k", "Up to 100,000 shots"), ("300k", "100,001-300,000 shots"),
        ("500k", "300,001-500,000 shots"), ("1m", "500,001-1,000,000 shots"),
        ("over_1m", "More than 1,000,000 shots"), ("tbd", "TBD"),
    ], default="tbd", tracking=True)

    x_machine_name = fields.Char(string="Proposed / Customer Machine", tracking=True)
    x_machine_tonnage = fields.Float(string="Machine Tonnage (T)", tracking=True)
    x_machine_shot_capacity_g = fields.Float(string="Shot Capacity (g)", tracking=True)
    x_tie_bar_x_mm = fields.Float(string="Tie-bar Spacing X (mm)", tracking=True)
    x_tie_bar_y_mm = fields.Float(string="Tie-bar Spacing Y (mm)", tracking=True)
    x_platen_x_mm = fields.Float(string="Platen Size X (mm)", tracking=True)
    x_platen_y_mm = fields.Float(string="Platen Size Y (mm)", tracking=True)
    x_machine_min_thickness_mm = fields.Float(string="Minimum Mould Thickness (mm)", tracking=True)
    x_machine_max_thickness_mm = fields.Float(string="Maximum Mould Thickness (mm)", tracking=True)
    x_machine_daylight_mm = fields.Float(string="Machine Daylight / Opening (mm)", tracking=True)
    x_machine_ejection_stroke_mm = fields.Float(string="Ejection Stroke (mm)", tracking=True)
    x_handling_capacity_kg = fields.Float(string="Crane / Handling Capacity (kg)", tracking=True)

    x_runner_brand = fields.Char(tracking=True)
    x_runner_weight_g = fields.Float(tracking=True)
    x_material_grade = fields.Char(string="Exact Material Grade", tracking=True)
    x_material_manufacturer = fields.Char(string="Resin Manufacturer / Brand", tracking=True)
    x_material_filler = fields.Char(string="Filler / Glass Fibre %", tracking=True)
    x_material_mfi = fields.Char(string="MFI / MFR", tracking=True)
    x_engineering_shrinkage = fields.Float(string="Engineering Shrinkage (%)", tracking=True)
    x_projected_area_cm2 = fields.Float(string="Projected Area per Cavity (cm2)", tracking=True)
    x_planner_tonnage = fields.Float(string="Planner Selected Tonnage (T)", tracking=True)
    x_dfm_reference = fields.Char(tracking=True)
    x_moldflow_reference = fields.Char(tracking=True)
    x_base_hardness = fields.Char(tracking=True)
    x_core_hardness = fields.Char(tracking=True)
    x_cavity_hardness = fields.Char(tracking=True)
    x_heat_treatment = fields.Selection([
        ("none", "None"), ("nitriding", "Nitriding"), ("vacuum", "Vacuum Hardening"),
        ("through", "Through Hardening"), ("other", "Other"), ("tbd", "TBD"),
    ], default="tbd", tracking=True)
    x_surface_treatment = fields.Selection([
        ("none", "None"), ("chrome", "Hard Chrome"), ("pvd", "PVD"),
        ("dlc", "DLC"), ("other", "Other"),
    ], default="none", tracking=True)

    x_toolmaker = fields.Char(string="Toolmaker / Supplier", tracking=True)
    x_tool_design_reference = fields.Char(tracking=True)
    x_engineering_approved_by = fields.Char(string="Engineering Approved By", tracking=True)
    x_engineering_approval_date = fields.Date(tracking=True)
    x_steel_go_ahead = fields.Boolean(tracking=True)
    x_dfm_approved = fields.Boolean(tracking=True)
    x_moldflow_approved = fields.Boolean(tracking=True)
    x_moldflow_not_applicable = fields.Boolean(tracking=True)
    x_tool_design_approved = fields.Boolean(tracking=True)
    x_final_cavitation_approved = fields.Boolean(tracking=True)
    x_runner_gate_approved = fields.Boolean(tracking=True)
    x_tool_steel_approved = fields.Boolean(tracking=True)
    x_cooling_frozen = fields.Boolean(tracking=True)
    x_ejection_frozen = fields.Boolean(tracking=True)
    x_major_risks_accepted = fields.Boolean(tracking=True)

    x_as_built_configuration = fields.Selection(
        [("single", "Single Cavity"), ("multi", "Multi Cavity"), ("family", "Family Mould")], tracking=True
    )
    x_as_built_special_technology = fields.Selection([
        ("none", "None"), ("two_k", "2K / Multi-material"), ("insert", "Insert Moulding"),
        ("overmould", "Overmoulding"), ("stack", "Stack Mould"), ("other", "Other"),
    ], tracking=True)
    x_actual_cavitation = fields.Char(tracking=True)
    x_actual_runner = fields.Selection([("hot", "Hot Runner"), ("cold", "Cold Runner"), ("hybrid", "Hybrid")], tracking=True)
    x_actual_gate = fields.Char(tracking=True)
    x_actual_steel = fields.Char(string="Actual Steel (Core / Cavity / Base)", tracking=True)
    x_as_built_length_mm = fields.Float(tracking=True)
    x_as_built_width_mm = fields.Float(tracking=True)
    x_as_built_height_mm = fields.Float(tracking=True)
    x_as_built_weight_kg = fields.Float(tracking=True)
    x_trial_reference = fields.Char(tracking=True)
    x_buyoff_reference = fields.Char(string="Buy-off Reference", tracking=True)
    x_dispatch_status = fields.Selection(
        [("dispatched", "Dispatched"), ("delivered", "Delivered"), ("installed", "Installed")], tracking=True
    )
    x_final_ecn_history = fields.Text(string="Final ECN / Change History", tracking=True)
    x_final_acceptance = fields.Boolean(tracking=True)

    x_baseline_confirmed = fields.Boolean(readonly=True, copy=False, tracking=True)
    x_baseline_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    x_baseline_date = fields.Datetime(readonly=True, copy=False)
    x_baseline_revision = fields.Char(readonly=True, copy=False)
    x_baseline_note = fields.Text(readonly=True, copy=False)
    x_change_reason = fields.Text(string="Reason for Controlled Change", copy=False)
    x_change_log_ids = fields.One2many("hjig.mould.change.log", "mould_id", string="Controlled Change History")
    x_geometry_ids = fields.One2many("hjig.mould.geometry", "mould_id", string="KRT Geometry Groups")

    x_total_cavities = fields.Integer(compute="_compute_engineering_checks")
    x_total_shot_weight_g = fields.Float(compute="_compute_engineering_checks")
    x_required_tonnage = fields.Float(compute="_compute_engineering_checks")
    x_machine_verdict = fields.Selection(
        [("na", "Not Evaluated"), ("pass", "PASS"), ("warn", "WARNING"), ("fail", "FAIL")],
        compute="_compute_engineering_checks",
    )
    x_machine_check_details = fields.Text(compute="_compute_engineering_checks")
    x_stage_ready = fields.Boolean(compute="_compute_stage_readiness")
    x_stage_blockers = fields.Text(compute="_compute_stage_readiness")

    _CONTROLLED_LIFECYCLE_FIELDS = {
        "x_mould_configuration", "x_cavitation", "x_special_technology", "x_grouping_basis",
        "x_mould_length_mm", "x_mould_width_mm", "x_mould_height_mm", "x_estimated_weight_kg",
        "x_runner_brand", "x_runner_weight_g", "x_material_grade", "x_engineering_shrinkage",
        "x_projected_area_cm2", "x_planner_tonnage", "x_dfm_reference", "x_moldflow_reference",
        "x_base_hardness", "x_core_hardness", "x_cavity_hardness", "x_heat_treatment",
        "x_surface_treatment", "x_toolmaker", "x_tool_design_reference",
    }
    _LIFECYCLE_MUTABLE_FIELDS = {
        name for name in (
            "x_mould_image x_lifecycle_stage x_special_technology x_planning_confidence x_grouping_basis "
            "x_planning_assumption x_open_technical_question x_customer_input_pending x_engineering_input_pending "
            "x_risk_flag x_risk_note x_cavity_engineering_justification x_cavitation_confirmed "
            "x_mould_length_mm x_mould_width_mm x_mould_height_mm x_estimated_weight_kg x_target_tool_life "
            "x_machine_name x_machine_tonnage x_machine_shot_capacity_g x_tie_bar_x_mm x_tie_bar_y_mm "
            "x_platen_x_mm x_platen_y_mm x_machine_min_thickness_mm x_machine_max_thickness_mm "
            "x_machine_daylight_mm x_machine_ejection_stroke_mm x_handling_capacity_kg x_runner_brand "
            "x_runner_weight_g x_material_grade x_material_manufacturer x_material_filler x_material_mfi "
            "x_engineering_shrinkage x_projected_area_cm2 x_planner_tonnage x_dfm_reference x_moldflow_reference "
            "x_base_hardness x_core_hardness x_cavity_hardness x_heat_treatment x_surface_treatment "
            "x_toolmaker x_tool_design_reference x_engineering_approved_by x_engineering_approval_date "
            "x_steel_go_ahead x_dfm_approved x_moldflow_approved x_moldflow_not_applicable x_tool_design_approved "
            "x_final_cavitation_approved x_runner_gate_approved x_tool_steel_approved x_cooling_frozen "
            "x_ejection_frozen x_major_risks_accepted x_as_built_configuration x_as_built_special_technology "
            "x_actual_cavitation x_actual_runner x_actual_gate x_actual_steel x_as_built_length_mm "
            "x_as_built_width_mm x_as_built_height_mm x_as_built_weight_kg x_trial_reference x_buyoff_reference "
            "x_dispatch_status x_final_ecn_history x_final_acceptance x_change_reason"
        ).split()
    }

    @api.depends(
        "x_cavitation", "x_part_ids.x_part_weight_grams", "x_part_ids.x_cavity_plan",
        "x_geometry_ids.cavity_quantity", "x_geometry_ids.part_ids.x_part_weight_grams",
        "x_part_ids.x_material_master_id", "x_projected_area_cm2", "x_machine_tonnage",
        "x_machine_shot_capacity_g", "x_runner_weight_g", "x_mould_length_mm", "x_mould_width_mm",
        "x_mould_height_mm", "x_tie_bar_x_mm", "x_tie_bar_y_mm", "x_platen_x_mm", "x_platen_y_mm",
        "x_machine_min_thickness_mm", "x_machine_max_thickness_mm", "x_machine_daylight_mm",
        "x_estimated_weight_kg", "x_handling_capacity_kg",
    )
    def _compute_engineering_checks(self):
        for mould in self:
            try:
                total_cavities = (
                    sum(mould.x_geometry_ids.mapped("cavity_quantity"))
                    if mould.x_mould_configuration == "family" and mould.x_geometry_ids
                    else sum(mould.x_part_ids.mapped("x_cavity_plan"))
                    if mould.x_mould_configuration == "family"
                    else int(mould.x_cavitation or 0)
                )
            except (TypeError, ValueError):
                total_cavities = 0
            total_cavities = max(total_cavities, 0)
            if mould.x_mould_configuration == "family" and mould.x_geometry_ids:
                shot = sum(
                    max(geometry.part_ids.mapped("x_part_weight_grams") or [0.0]) * geometry.cavity_quantity
                    for geometry in mould.x_geometry_ids
                ) + (mould.x_runner_weight_g or 0.0)
            else:
                shot = sum((part.x_part_weight_grams or 0.0) * (part.x_cavity_plan or 1) for part in mould.x_part_ids) + (mould.x_runner_weight_g or 0.0)
            material = mould.x_part_ids[:1].x_material_master_id
            factor = 0.0
            for candidate in ("tonnage_factor", "recommended_tonnage"):
                value = getattr(material, candidate, False)
                try:
                    factor = float(value or 0.0)
                    if factor:
                        break
                except (TypeError, ValueError):
                    continue
            required_tonnage = math.ceil(((mould.x_projected_area_cm2 * max(total_cavities, 1)) / 6.4516) * factor) if factor else (mould.x_planner_tonnage or 0.0)
            checks = []
            def add(label, state, detail):
                checks.append((label, state, detail))
            if required_tonnage and mould.x_machine_tonnage:
                ratio = mould.x_machine_tonnage / required_tonnage
                add("Clamp tonnage", "pass" if ratio >= 1.1 else "warn" if ratio >= 1 else "fail", f"Required {required_tonnage:.0f} T; machine {mould.x_machine_tonnage:.0f} T")
            else:
                add("Clamp tonnage", "na", "Projected area/material factor and machine tonnage are required")
            if shot and mould.x_machine_shot_capacity_g:
                usage = 100 * shot / mould.x_machine_shot_capacity_g
                add("Shot capacity", "pass" if usage <= 80 else "warn" if usage <= 95 else "fail", f"{shot:.1f} g / {mould.x_machine_shot_capacity_g:.1f} g ({usage:.0f}%)")
            else:
                add("Shot capacity", "na", "Part weights and machine shot capacity are required")
            if all((mould.x_mould_length_mm, mould.x_mould_width_mm, mould.x_tie_bar_x_mm, mould.x_tie_bar_y_mm)):
                direct = mould.x_mould_length_mm <= mould.x_tie_bar_x_mm and mould.x_mould_width_mm <= mould.x_tie_bar_y_mm
                diagonal = mould.x_mould_length_mm <= mould.x_tie_bar_x_mm * 1.4 and mould.x_mould_width_mm <= mould.x_tie_bar_y_mm * 1.4
                add("Tie-bar fit", "pass" if direct else "warn" if diagonal else "fail", f"Mould {mould.x_mould_length_mm:.0f}x{mould.x_mould_width_mm:.0f}; tie-bars {mould.x_tie_bar_x_mm:.0f}x{mould.x_tie_bar_y_mm:.0f} mm")
            else:
                add("Tie-bar fit", "na", "Mould footprint and tie-bar spacing are required")
            if all((mould.x_mould_length_mm, mould.x_mould_width_mm, mould.x_platen_x_mm, mould.x_platen_y_mm)):
                passed = mould.x_mould_length_mm <= mould.x_platen_x_mm and mould.x_mould_width_mm <= mould.x_platen_y_mm
                add("Platen fit", "pass" if passed else "fail", f"Platen {mould.x_platen_x_mm:.0f}x{mould.x_platen_y_mm:.0f} mm")
            else:
                add("Platen fit", "na", "Mould footprint and platen size are required")
            if mould.x_mould_height_mm and (mould.x_machine_min_thickness_mm or mould.x_machine_max_thickness_mm):
                passed = (not mould.x_machine_min_thickness_mm or mould.x_mould_height_mm >= mould.x_machine_min_thickness_mm) and (not mould.x_machine_max_thickness_mm or mould.x_mould_height_mm <= mould.x_machine_max_thickness_mm)
                add("Mould thickness", "pass" if passed else "fail", f"Stack {mould.x_mould_height_mm:.0f} mm")
            else:
                add("Mould thickness", "na", "Stack height and machine limits are required")
            if mould.x_mould_height_mm and mould.x_machine_daylight_mm:
                ratio = mould.x_machine_daylight_mm / mould.x_mould_height_mm
                add("Daylight", "pass" if ratio >= 1.5 else "warn" if ratio >= 1.2 else "fail", f"Daylight {mould.x_machine_daylight_mm:.0f} mm; stack {mould.x_mould_height_mm:.0f} mm")
            else:
                add("Daylight", "na", "Stack height and daylight are required")
            if mould.x_estimated_weight_kg and mould.x_handling_capacity_kg:
                add("Handling capacity", "pass" if mould.x_handling_capacity_kg >= mould.x_estimated_weight_kg else "fail", f"Mould {mould.x_estimated_weight_kg:.0f} kg; capacity {mould.x_handling_capacity_kg:.0f} kg")
            else:
                add("Handling capacity", "na", "Mould weight and handling capacity are required")
            states = [state for _label, state, _detail in checks]
            verdict = "fail" if "fail" in states else "na" if all(state == "na" for state in states) else "warn" if any(state in ("warn", "na") for state in states) else "pass"
            mould.x_total_cavities = total_cavities
            mould.x_total_shot_weight_g = shot
            mould.x_required_tonnage = required_tonnage
            mould.x_machine_verdict = verdict
            mould.x_machine_check_details = "\n".join(f"{label}: {state.upper()} - {detail}" for label, state, detail in checks)

    @api.depends(
        "x_lifecycle_stage", "x_part_ids", "x_part_ids.x_missing_fields", "x_part_ids.x_part_material", "x_part_ids.x_colour",
        "x_part_ids.x_geometry_id", "x_geometry_ids", "x_geometry_ids.cavity_quantity",
        "x_planning_assumption", "x_grouping_basis", "x_risk_flag", "x_risk_note", "x_baseline_confirmed",
        "x_cavitation_confirmed", "x_mould_length_mm", "x_mould_width_mm", "x_mould_height_mm",
        "x_machine_verdict", "x_material_grade", "x_engineering_shrinkage", "x_projected_area_cm2",
        "x_planner_tonnage", "x_dfm_reference", "x_toolmaker", "x_tool_design_reference",
        "x_engineering_approved_by", "x_engineering_approval_date", "x_steel_go_ahead",
        "x_dfm_approved", "x_tool_design_approved", "x_final_cavitation_approved", "x_runner_gate_approved",
        "x_tool_steel_approved", "x_cooling_frozen", "x_ejection_frozen", "x_major_risks_accepted",
        "x_actual_cavitation", "x_actual_gate", "x_actual_steel", "x_final_acceptance",
    )
    def _compute_stage_readiness(self):
        for mould in self:
            blockers = []
            if not mould.x_part_ids:
                blockers.append(_("Capture at least one active part."))
            if mould.x_part_ids.filtered(lambda part: part.x_missing_fields):
                blockers.append(_("Complete all mandatory part identity and planning fields."))
            if not mould.x_planning_assumption:
                blockers.append(_("Document the planning assumption."))
            if mould.x_mould_configuration == "family":
                if not mould.x_grouping_basis:
                    blockers.append(_("Document the family-mould grouping basis."))
                active_parts = mould.x_part_ids.filtered("x_active")
                groups = mould.x_geometry_ids.filtered("active")
                if len(groups) < 2:
                    blockers.append(_("A family mould requires at least two controlled geometry groups."))
                if active_parts.filtered(lambda part: not part.x_geometry_id):
                    blockers.append(_("Assign every active family-mould part to a controlled geometry group."))
                # The approved planning prototype makes material and colour a
                # mould-wide family rule.  It is unsafe to approve separate
                # geometry groups that silently use different inputs.
                missing_material = active_parts.filtered(
                    lambda part: not (part.x_part_material or "").strip()
                )
                missing_colour = active_parts.filtered(
                    lambda part: not (part.x_colour or "").strip()
                )
                materials = {
                    (part.x_part_material or "").strip().casefold()
                    for part in active_parts if (part.x_part_material or "").strip()
                }
                colours = {
                    (part.x_colour or "").strip().casefold()
                    for part in active_parts if (part.x_colour or "").strip()
                }
                if missing_material:
                    blockers.append(_("Every active family-mould part requires a confirmed material."))
                if missing_colour:
                    blockers.append(_("Every active family-mould part requires a confirmed colour."))
                if len(materials) > 1:
                    blockers.append(_("All active family-mould parts must use one common material."))
                if len(colours) > 1:
                    blockers.append(_("All active family-mould parts must use one common colour."))
                for group in groups:
                    parts = group.part_ids.filtered("x_active")
                    if not parts:
                        blockers.append(_("Every active family geometry group must contain at least one part."))
                    if len(set(parts.mapped("x_part_material"))) > 1 or len(set(parts.mapped("x_colour"))) > 1:
                        blockers.append(_("Every family geometry group must use one material and one colour."))
            if mould.x_risk_flag and not mould.x_risk_note:
                blockers.append(_("Record a risk note for the flagged risk."))
            if STAGE_ORDER[mould.x_lifecycle_stage] >= STAGE_ORDER["tg01"]:
                if not mould.x_baseline_confirmed:
                    blockers.append(_("Confirm the TG-01 part and mould architecture baseline."))
                if not mould.x_cavitation_confirmed:
                    blockers.append(_("Confirm the planning cavitation."))
            if STAGE_ORDER[mould.x_lifecycle_stage] >= STAGE_ORDER["tg02"]:
                required = [
                    (mould.x_mould_length_mm and mould.x_mould_width_mm and mould.x_mould_height_mm, _("Estimate mould L x W x H.")),
                    (mould.x_machine_verdict != "na", _("Enter machine data and evaluate compatibility.")),
                    (mould.x_machine_verdict != "fail", _("Resolve failed machine compatibility checks.")),
                    (mould.x_material_grade, _("Confirm the exact material grade.")),
                    (mould.x_engineering_shrinkage, _("Confirm engineering shrinkage.")),
                    (mould.x_projected_area_cm2, _("Record projected area.")),
                    (mould.x_planner_tonnage, _("Record planner-selected tonnage.")),
                    (mould.x_dfm_reference, _("Link the DFM reference.")),
                ]
                blockers.extend(message for passed, message in required if not passed)
            if STAGE_ORDER[mould.x_lifecycle_stage] >= STAGE_ORDER["tg03"]:
                required = [
                    (mould.x_estimated_weight_kg, _("Freeze final mould weight.")),
                    (mould.x_machine_verdict == "pass", _("Machine compatibility must be PASS.")),
                    (mould.x_target_tool_life != "tbd", _("Freeze target tool life.")),
                    (mould.x_core_hardness and mould.x_cavity_hardness and mould.x_heat_treatment != "tbd", _("Freeze steel hardness and heat treatment.")),
                    (mould.x_toolmaker, _("Record the toolmaker.")),
                    (mould.x_tool_design_reference, _("Record the tool-design reference.")),
                    (mould.x_engineering_approved_by and mould.x_engineering_approval_date, _("Record engineering approval authority and date.")),
                    (mould.x_steel_go_ahead, _("Record steel go-ahead.")),
                    (mould.x_dfm_approved and mould.x_tool_design_approved and mould.x_final_cavitation_approved, _("Complete DFM, design and cavitation approvals.")),
                    (mould.x_runner_gate_approved and mould.x_tool_steel_approved, _("Approve runner/gate and tool steel.")),
                    (mould.x_cooling_frozen and mould.x_ejection_frozen and mould.x_major_risks_accepted, _("Freeze cooling/ejection and accept or close major risks.")),
                    (mould.x_moldflow_approved or mould.x_moldflow_not_applicable, _("Approve Moldflow or mark it not applicable.")),
                ]
                blockers.extend(message for passed, message in required if not passed)
            if mould.x_lifecycle_stage == "closure":
                required = [
                    (mould.x_as_built_configuration and mould.x_actual_cavitation, _("Record the as-built configuration and cavitation.")),
                    (mould.x_actual_runner and mould.x_actual_gate and mould.x_actual_steel, _("Record actual runner, gate and steels.")),
                    (mould.x_as_built_length_mm and mould.x_as_built_width_mm and mould.x_as_built_height_mm and mould.x_as_built_weight_kg, _("Record as-built size and weight.")),
                    (mould.x_trial_reference and mould.x_buyoff_reference, _("Record trial and buy-off references.")),
                    (mould.x_dispatch_status, _("Record dispatch / installation status.")),
                    (mould.x_final_acceptance, _("Record final acceptance.")),
                ]
                blockers.extend(message for passed, message in required if not passed)
            mould.x_stage_blockers = "\n".join(f"- {message}" for message in blockers)
            mould.x_stage_ready = not blockers

    def write(self, vals):
        if self.env.context.get("allow_mould_lifecycle_control"):
            return super().write(vals)
        for mould in self:
            changed = self._CONTROLLED_LIFECYCLE_FIELDS.intersection(vals)
            if changed and STAGE_ORDER.get(mould.x_lifecycle_stage, 0) >= STAGE_ORDER["tg01"]:
                reason = (vals.get("x_change_reason") or mould.x_change_reason or "").strip()
                if not reason:
                    raise ValidationError(_("A controlled-change reason is required from TG-01 onward."))
                old_values = {field_name: mould[field_name] for field_name in changed}
                result = super(HjigMouldLifecycle, mould.with_context(allow_native_form_workflow=True)).write(vals)
                for field_name in changed:
                    mould.env["hjig.mould.change.log"].create({
                        "mould_id": mould.id,
                        "part_id": False,
                        "field_name": field_name,
                        "old_value": str(old_values[field_name] or ""),
                        "new_value": str(mould[field_name] or ""),
                        "reason": reason,
                        "lifecycle_stage": mould.x_lifecycle_stage,
                        "revision": mould.x_plan_revision,
                    })
                if {"x_mould_configuration", "x_cavitation", "x_grouping_basis"}.intersection(changed):
                    mould.with_context(allow_native_form_workflow=True, allow_mould_lifecycle_control=True).write({
                        "x_baseline_confirmed": False,
                        "x_baseline_note": _("Baseline invalidated by a controlled architecture change."),
                    })
                return result
        if self._LIFECYCLE_MUTABLE_FIELDS.intersection(vals):
            return super(HjigMouldLifecycle, self.with_context(
                allow_native_form_workflow=True,
                allow_mould_lifecycle_control=True,
            )).write(vals)
        return super().write(vals)

    def action_confirm_architecture_baseline(self):
        for mould in self:
            if not mould.x_part_ids or mould.x_part_ids.filtered(lambda part: part.x_missing_fields):
                raise ValidationError(_("Complete all active parts before confirming the architecture baseline."))
            mould.with_context(allow_native_form_workflow=True, allow_mould_lifecycle_control=True).write({
                "x_baseline_confirmed": True,
                "x_baseline_by_id": self.env.user.id,
                "x_baseline_date": fields.Datetime.now(),
                "x_baseline_revision": mould.x_plan_revision,
                "x_baseline_note": False,
            })

    def action_advance_lifecycle(self):
        next_stage = {"ig01": "tg01", "tg01": "tg02", "tg02": "tg03", "tg03": "closure"}
        for mould in self:
            if not mould.x_stage_ready:
                raise ValidationError(_("This stage is not ready:\n%s") % mould.x_stage_blockers)
            target = next_stage.get(mould.x_lifecycle_stage)
            if not target:
                raise UserError(_("The mould lifecycle is already at Closure."))
            mould.with_context(allow_native_form_workflow=True, allow_mould_lifecycle_control=True).write({
                "x_lifecycle_stage": target,
                "x_change_reason": False,
            })


class HjigMouldPartLifecycle(models.Model):
    _inherit = "x_mould_part"

    x_colour = fields.Char(string="Colour", tracking=True)
    x_dimension_x_mm = fields.Float(string="Part X (mm) - Moulding Orientation", tracking=True)
    x_dimension_y_mm = fields.Float(string="Part Y (mm) - Moulding Orientation", tracking=True)
    x_dimension_z_mm = fields.Float(string="Part Z (mm) - Moulding Orientation", tracking=True)
    x_geometry_group = fields.Char(string="KRT Geometry Group", tracking=True)
    x_geometry_id = fields.Many2one(
        "hjig.mould.geometry", string="Controlled KRT Geometry Group", ondelete="restrict", tracking=True,
        domain="[('mould_id', '=', x_mould_id), ('active', '=', True)]",
    )
    x_remarks = fields.Text(tracking=True)
    x_deactivation_reason = fields.Char(tracking=True)
    x_change_reason = fields.Text(string="Reason for Controlled Change", copy=False)

    _CONTROLLED_PART_FIELDS = {
        "x_material_master_id", "x_part_material", "x_colour", "x_qps", "x_dimension_x_mm",
        "x_dimension_y_mm", "x_dimension_z_mm", "x_surface_finish_id", "x_surface_grade_code",
        "x_cavity_plan", "x_geometry_group", "x_geometry_id", "x_mould_id",
    }

    def write(self, vals):
        if self.env.context.get("allow_mould_lifecycle_control"):
            return super().write(vals)
        for part in self:
            changed = self._CONTROLLED_PART_FIELDS.intersection(vals)
            if changed and STAGE_ORDER.get(part.x_mould_id.x_lifecycle_stage, 0) >= STAGE_ORDER["tg01"]:
                reason = (vals.get("x_change_reason") or part.x_change_reason or "").strip()
                if not reason:
                    raise ValidationError(_("A controlled-change reason is required for part changes from TG-01 onward."))
                old_values = {field_name: part[field_name] for field_name in changed}
                result = super(HjigMouldPartLifecycle, part.with_context(allow_mould_lifecycle_control=True)).write(vals)
                for field_name in changed:
                    part.env["hjig.mould.change.log"].create({
                        "mould_id": part.x_mould_id.id,
                        "part_id": part.id,
                        "field_name": field_name,
                        "old_value": str(old_values[field_name] or ""),
                        "new_value": str(part[field_name] or ""),
                        "reason": reason,
                        "lifecycle_stage": part.x_mould_id.x_lifecycle_stage,
                        "revision": part.x_mould_id.x_plan_revision,
                    })
                part.x_mould_id.with_context(allow_native_form_workflow=True, allow_mould_lifecycle_control=True).write({
                    "x_baseline_confirmed": False,
                    "x_baseline_note": _("Baseline invalidated by a controlled part change."),
                })
                return result
        return super().write(vals)


class HjigMouldChangeLog(models.Model):
    _name = "hjig.mould.change.log"
    _description = "Mould Planning Controlled Change"
    _order = "change_date desc, id desc"

    mould_id = fields.Many2one("x_mould", required=True, ondelete="restrict", index=True)
    project_id = fields.Many2one(related="mould_id.x_project_id", store=True, index=True)
    part_id = fields.Many2one("x_mould_part", ondelete="restrict")
    field_name = fields.Char(required=True)
    old_value = fields.Text()
    new_value = fields.Text()
    reason = fields.Text(required=True)
    lifecycle_stage = fields.Selection(LIFECYCLE_STAGES, required=True)
    revision = fields.Char(required=True)
    changed_by_id = fields.Many2one("res.users", default=lambda self: self.env.user, required=True)
    change_date = fields.Datetime(default=fields.Datetime.now, required=True)

    def write(self, vals):
        raise UserError(_("Controlled mould change history is immutable."))

    def unlink(self):
        raise UserError(_("Controlled mould change history cannot be deleted."))


class HjigMouldGeometry(models.Model):
    _name = "hjig.mould.geometry"
    _description = "Controlled Family-Mould Geometry Group"
    _order = "mould_id, sequence, id"

    mould_id = fields.Many2one("x_mould", required=True, ondelete="restrict", index=True)
    project_id = fields.Many2one(related="mould_id.x_project_id", store=True, index=True)
    sequence = fields.Integer(default=10, required=True)
    code = fields.Char(required=True, tracking=True)
    name = fields.Char(required=True, tracking=True)
    cavity_quantity = fields.Integer(default=1, required=True, tracking=True)
    part_ids = fields.One2many("x_mould_part", "x_geometry_id", string="Parts")
    active = fields.Boolean(default=True, tracking=True)
    krt_label = fields.Char(compute="_compute_krt_label")
    material_colour_summary = fields.Char(compute="_compute_krt_label")

    _mould_geometry_code_unique = models.Constraint(
        "UNIQUE(mould_id, code)", "The geometry-group code must be unique within one mould."
    )

    @api.depends("cavity_quantity", "part_ids.x_part_material", "part_ids.x_colour")
    def _compute_krt_label(self):
        for geometry in self:
            geometry.krt_label = "1x%s" % geometry.cavity_quantity
            materials = sorted(set(filter(None, geometry.part_ids.mapped("x_part_material"))))
            colours = sorted(set(filter(None, geometry.part_ids.mapped("x_colour"))))
            geometry.material_colour_summary = "%s / %s" % (", ".join(materials) or "TBD", ", ".join(colours) or "TBD")

    @api.constrains("cavity_quantity")
    def _check_cavity_quantity(self):
        if self.filtered(lambda item: item.cavity_quantity < 1):
            raise ValidationError(_("Geometry cavity quantity must be at least one."))

    def write(self, vals):
        controlled = {"code", "cavity_quantity", "active"}.intersection(vals)
        for geometry in self:
            if controlled and STAGE_ORDER.get(geometry.mould_id.x_lifecycle_stage, 0) >= STAGE_ORDER["tg01"]:
                reason = (self.env.context.get("mould_change_reason") or geometry.mould_id.x_change_reason or "").strip()
                if not reason:
                    raise ValidationError(_("A controlled-change reason is required to change a TG-01 geometry group."))
                old_values = {field_name: geometry[field_name] for field_name in controlled}
                result = super(HjigMouldGeometry, geometry).write(vals)
                for field_name in controlled:
                    geometry.env["hjig.mould.change.log"].create({
                        "mould_id": geometry.mould_id.id,
                        "field_name": "geometry.%s.%s" % (geometry.code, field_name),
                        "old_value": str(old_values[field_name] or ""),
                        "new_value": str(geometry[field_name] or ""),
                        "reason": reason,
                        "lifecycle_stage": geometry.mould_id.x_lifecycle_stage,
                        "revision": geometry.mould_id.x_plan_revision,
                    })
                geometry.mould_id.with_context(allow_native_form_workflow=True, allow_mould_lifecycle_control=True).write({
                    "x_baseline_confirmed": False,
                    "x_baseline_note": _("Baseline invalidated by a controlled KRT geometry change."),
                })
                return result
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda item: STAGE_ORDER.get(item.mould_id.x_lifecycle_stage, 0) >= STAGE_ORDER["tg01"]):
            raise UserError(_("Archive controlled geometry groups instead of deleting them."))
        return super().unlink()


class HjigProjectImageEvidence(models.Model):
    _inherit = "hjig.evidence.link"

    image_1920 = fields.Image(string="Validation Image", attachment=True, tracking=True)
    image_caption = fields.Char(tracking=True)
    image_stage = fields.Selection(LIFECYCLE_STAGES + [("other", "Other B-Series Stage")], tracking=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("image_1920") and not vals.get("attachment_id") and not vals.get("source_url"):
                vals["source_url"] = "odoo-image://governed-evidence"
        return super().create(vals_list)

    @api.constrains("attachment_id", "source_url", "image_1920")
    def _check_evidence_source(self):
        for evidence in self:
            if not evidence.attachment_id and not evidence.image_1920 and not (evidence.source_url or "").strip():
                raise ValidationError(_("Evidence requires an image, attachment, or source link."))


class ProjectProjectImageEvidence(models.Model):
    _inherit = "project.project"

    hjig_image_evidence_count = fields.Integer(compute="_compute_hjig_image_evidence_count")

    def _compute_hjig_image_evidence_count(self):
        grouped = self.env["hjig.evidence.link"]._read_group(
            [("project_id", "in", self.ids), ("image_1920", "!=", False)], ["project_id"], ["__count"]
        )
        counts = {project.id: count for project, count in grouped}
        for project in self:
            project.hjig_image_evidence_count = counts.get(project.id, 0)

    def action_open_hjig_image_evidence(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Project Images & Visual Evidence"),
            "res_model": "hjig.evidence.link",
            "view_mode": "kanban,list,form",
            "domain": [("project_id", "=", self.id), ("image_1920", "!=", False)],
            "context": {"default_project_id": self.id, "default_evidence_type": "Project Validation Image"},
        }
