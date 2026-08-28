# -*- coding: utf-8 -*-
"""Founder-approved B-Series dependency authority.

This module deliberately rebuilds draft dependency maps from the controlled
v1.4 specification.  The superseded v1.2 snapshot rules are migration evidence,
not execution authority.
"""

from odoo import _, models
from odoo.exceptions import ValidationError


SOURCE_REFERENCE = "PN_CTL_Activity_Dependencies_Specification_v1.4"
SOURCE_VERSION = "v1.4 / Founder approved 21-Aug-2026"


# Only genuine output dependencies belong here.  Numeric listing order is not a
# dependency.  Gate boundaries are added separately as compact convergence and
# entry barriers.
COMMON_RULES = (
    ("A-006", "A-007", "sequential"),
    ("A-007", "A-008", "design_maturity"),
    ("A-007", "A-009", "design_maturity"),
    ("A-007", "A-010", "design_maturity"),
    ("A-008", "A-011", "design_signoff_input"),
    ("A-009", "A-011", "design_signoff_input"),
    ("A-010", "A-011", "design_signoff_input"),
    ("A-014", "A-015", "sequential"),
    ("A-015", "A-016", "sequential"),
    ("A-016", "A-017", "sequential"),
    ("A-019", "A-022", "steel_go_readiness"),
    ("A-020", "A-022", "conditional_steel_go_readiness"),
    ("A-021", "A-022", "steel_go_readiness"),
    ("A-022", "A-023", "steel_go_release"),
    ("A-023", "A-025", "manufacturing_readiness"),
    ("A-025", "A-032", "manufacturing_completion"),
    ("A-034", "A-036", "trial_readiness"),
    ("A-035", "A-036", "trial_readiness"),
    ("A-036", "A-037", "sequential"),
    ("A-037", "A-038", "sequential"),
    ("A-038", "A-039", "sample_availability"),
    ("A-038", "A-040", "sample_availability"),
    ("A-038", "A-041", "conditional_sample_availability"),
    ("A-039", "A-042", "inspection_aggregation"),
    ("A-040", "A-042", "inspection_aggregation"),
    ("A-041", "A-042", "conditional_inspection_aggregation"),
    ("A-042", "A-043", "consolidated_feedback"),
    ("A-043", "A-044", "change_control"),
    ("A-044", "A-045", "change_control"),
    ("A-045", "A-046", "correction_sequence"),
    ("A-046", "A-047", "correction_sequence"),
    ("A-047", "A-048", "sequential"),
    ("A-048", "A-049", "sequential"),
    ("A-049", "A-050", "sample_availability"),
    ("A-049", "A-051", "sample_availability"),
    ("A-049", "A-052", "conditional_sample_availability"),
    ("A-050", "A-053", "inspection_aggregation"),
    ("A-051", "A-053", "inspection_aggregation"),
    ("A-052", "A-053", "conditional_inspection_aggregation"),
    ("A-053", "A-054", "customer_acknowledgement"),
    ("A-053", "A-055A", "surface_finish_governance"),
    ("A-054", "A-055", "corrective_action"),
    ("A-055A", "A-055B", "surface_finish_governance"),
    ("A-055", "A-056", "trial_readiness"),
    ("A-055B", "A-056", "trial_readiness"),
    ("A-056", "A-057", "final_buyoff"),
    ("A-057", "A-058", "final_buyoff_report"),
    ("A-057", "A-059", "final_buyoff_report"),
    ("A-057", "A-060", "final_buyoff_report"),
    ("A-057", "A-061", "final_buyoff_report"),
    ("A-057", "A-062", "final_buyoff_report"),
    ("A-057", "A-063", "conditional_final_buyoff_report"),
    ("A-057", "A-066", "dispatch_readiness"),
    ("A-058", "A-033", "surface_protection_readiness"),
    ("A-059", "A-033", "surface_protection_readiness"),
    ("A-060", "A-033", "surface_protection_readiness"),
    ("A-061", "A-033", "surface_protection_readiness"),
    ("A-062", "A-033", "surface_protection_readiness"),
    ("A-063", "A-033", "conditional_surface_protection_readiness"),
    ("A-033", "A-064", "packing_sequence"),
    ("A-064", "A-065", "packing_sequence"),
    ("A-066", "A-067", "dispatch_readiness"),
    ("A-067", "A-068", "dispatch_sequence"),
    ("A-068", "A-069", "logistics_sequence"),
    ("A-069", "A-070", "logistics_sequence"),
    ("A-068", "A-071", "logistics_sequence"),
    ("A-070", "A-072", "document_readiness"),
    ("A-071", "A-072", "document_readiness"),
    ("A-072", "A-073", "shipment_sequence"),
    ("A-073", "A-074", "shipment_sequence"),
    ("A-074", "A-075", "shipment_sequence"),
    ("A-075", "A-076", "shipment_tracking"),
    ("A-076", "A-077", "shipment_tracking"),
    ("A-077", "A-078", "boe_readiness"),
    ("A-078", "A-079", "parallel_boe_readiness"),
    ("A-079", "A-080", "boe_filing"),
    ("A-082", "A-083", "shipment_closure"),
    ("A-082", "A-084", "rbi_compliance"),
    ("A-085", "A-086", "installation_sequence"),
    ("A-086", "A-087", "installation_sequence"),
    ("A-087", "A-088", "issue_resolution"),
    ("A-088", "A-089", "final_comparison"),
    ("A-089", "A-090", "final_signoff"),
    ("A-090", "A-091", "final_payment_authorization"),
    ("A-090", "A-092", "testimonial_request"),
    ("B8-01", "B8-09", "closure_convergence"),
    ("B8-02", "B8-09", "closure_convergence"),
    ("B8-03", "B8-09", "closure_convergence"),
    ("B8-04", "B8-09", "closure_convergence"),
    ("B8-05", "B8-09", "closure_convergence"),
    ("B8-06", "B8-09", "closure_convergence"),
    ("B8-07", "B8-09", "closure_convergence"),
    ("B8-08", "B8-09", "closure_convergence"),
)


class HjigProgrammeTemplateVersion(models.Model):
    _inherit = "hjig.programme.template.version"

    def _sync_founder_approved_dependency_rules(self):
        """Replace superseded draft dependency data with v1.4 authority."""
        Dependency = self.env["hjig.programme.template.dependency.rule"]
        for version in self:
            if version.state != "draft":
                raise ValidationError(_("Dependency authority may be rebuilt only on a draft version."))
            if version.execution_mode != "governed_gates":
                continue

            activity_by_master = {}
            for activity in version.activity_line_ids:
                for code in (activity.legacy_master_codes or "").split(","):
                    code = code.strip().upper()
                    if code:
                        activity_by_master[code] = activity

            version.dependency_rule_ids.unlink()
            version.activity_line_ids.write({"predecessor_ids": [(5, 0, 0)]})
            represented = set()
            counter = 0

            def create_rule(predecessor, successor, rule_type, requirement, conditional=False):
                nonlocal counter
                if not predecessor or not successor or predecessor == successor:
                    return
                pair = (predecessor.id, successor.id)
                if pair in represented:
                    return
                if predecessor.sequence >= successor.sequence:
                    raise ValidationError(
                        _("Founder-approved dependency is not forward-only: %s -> %s")
                        % (predecessor.name, successor.name)
                    )
                counter += 1
                Dependency.create({
                    "version_id": version.id,
                    "legacy_source_rule_id": -140000 - counter,
                    "predecessor_activity_id": predecessor.id,
                    "successor_activity_id": successor.id,
                    "predecessor_basis": predecessor.execution_basis,
                    "successor_basis": successor.execution_basis,
                    "rule_type": rule_type,
                    "scope_matching_rule": "%s->%s (same programme run; governed scope)" % (
                        predecessor.execution_basis.upper(), successor.execution_basis.upper()
                    ),
                    "aggregation_requirement": requirement,
                    "conditional_handling": (
                        "A documented scope decision or approved waiver removes the conditional predecessor."
                        if conditional else "Not conditional."
                    ),
                    "source_reference": SOURCE_REFERENCE,
                    "source_version": SOURCE_VERSION,
                })
                successor.predecessor_ids = [(4, predecessor.id)]
                represented.add(pair)

            for predecessor_code, successor_code, rule_type in COMMON_RULES:
                create_rule(
                    activity_by_master.get(predecessor_code),
                    activity_by_master.get(successor_code),
                    rule_type,
                    "Complete the controlled predecessor output before starting the successor.",
                    "conditional" in rule_type,
                )

            # Programme-specific design and Pre-B2 routes.
            if version.template_id.code == "LGC":
                for predecessor_code, successor_code in (
                    ("A-011", "A-012"), ("A-011", "A-013"),
                    ("A-012", "A-014"), ("A-013", "A-014"),
                ):
                    create_rule(
                        activity_by_master.get(predecessor_code),
                        activity_by_master.get(successor_code),
                        "programme_route",
                        "LaunchGuard Complete design and foundation outputs must be controlled before toolmaker selection.",
                    )
            elif version.template_id.code in ("LGV", "TLC"):
                for predecessor_code, successor_code in (
                    ("A-012", "A-013"), ("A-013", "A-014"),
                ):
                    create_rule(
                        activity_by_master.get(predecessor_code),
                        activity_by_master.get(successor_code),
                        "pre_b2_route",
                        "Complete the controlled Pre-B2 predecessor output before continuing.",
                    )

            def named(prefix):
                upper_prefix = prefix.upper()
                return version.activity_line_ids.filtered(
                    lambda item: (item.name or "").upper().startswith(upper_prefix)
                )[:1]

            # Commercial controls explicitly governed by v1.4.
            cm05 = named("CM-05:")
            create_rule(
                activity_by_master.get("A-023"), cm05,
                "commercial_hard_block",
                "CM-05 may be collected after steel procurement and must be complete before T0 trial.",
            )
            create_rule(
                cm05, activity_by_master.get("A-036"),
                "commercial_hard_block",
                "CM-05 must be confirmed before T0 trial.",
            )
            cm06 = named("CM-06:")
            create_rule(
                activity_by_master.get("A-038"), cm06,
                "commercial_trigger",
                "CM-06 is triggered only after T0 samples are received in India.",
            )
            cm07 = named("CM-07:")
            create_rule(
                activity_by_master.get("A-067"), cm07,
                "commercial_trigger",
                "A-067 dispatch readiness is the CM-07 trigger; CM-07 must not wait for sail-off.",
            )
            cm08 = named("CM-08:")
            payment_verified = activity_by_master.get("A-081")
            cm09 = named("CM-09:")
            delivery = activity_by_master.get("A-082")
            create_rule(
                activity_by_master.get("A-078"), cm08,
                "parallel_boe_readiness",
                "CM-08 demand may progress in parallel with A-079 after A-078 BOE readiness.",
            )
            create_rule(
                cm08, payment_verified,
                "commercial_hard_block",
                "Customer duty demand must precede payment verification.",
            )
            create_rule(
                payment_verified, cm09,
                "commercial_hard_block",
                "Customer payment must be verified before HJIG pays agencies or the portal.",
            )
            create_rule(
                activity_by_master.get("A-080"), delivery,
                "customs_clearance",
                "Verified BOE filing must precede customs clearance and delivery.",
            )
            create_rule(
                cm09, delivery,
                "commercial_hard_block",
                "Agency payment must be complete before customs clearance and delivery.",
            )
            cm10 = named("CM-10:")
            create_rule(
                activity_by_master.get("A-090"), cm10,
                "commercial_trigger",
                "For Complete and Development, A-090 India Site Trial Sign-Off triggers CM-10.",
            )
            if version.template_id.code == "TLC" and cm10:
                dispatch_confirmation = version.activity_line_ids.filtered(
                    lambda item: "DISPATCH CONFIRMATION SIGN-OFF" in (item.name or "").upper()
                )[:1]
                create_rule(
                    dispatch_confirmation, cm10,
                    "commercial_trigger",
                    "For ToolLock Control, Dispatch Confirmation Sign-Off triggers CM-10.",
                )
            cm11 = named("CM-11:")
            create_rule(
                cm11, activity_by_master.get("B8-09"),
                "commercial_hard_block",
                "CM-11 is the sole actual final 5% release and must complete before project closure.",
            )

            # Compact gate supremacy: all work converges on the final gate-control
            # activity, then that single control blocks every activity in the next
            # gate.  This preserves the gate without the old N x M dependency mesh.
            gates = version.gate_line_ids.filtered("required").sorted("sequence")
            for previous_gate, next_gate in zip(gates, gates[1:]):
                previous_activities = version.activity_line_ids.filtered(
                    lambda item: item.gate_line_id == previous_gate
                ).sorted("sequence")
                next_activities = version.activity_line_ids.filtered(
                    lambda item: item.gate_line_id == next_gate
                ).sorted("sequence")
                if not previous_activities or not next_activities:
                    continue
                exit_control = previous_activities[-1]
                for activity in previous_activities[:-1]:
                    create_rule(
                        activity, exit_control,
                        "gate_exit_barrier",
                        "All applicable activities in the gate must complete before its exit control.",
                        activity.conditional,
                    )
                for activity in next_activities:
                    create_rule(
                        exit_control, activity,
                        "gate_entry_barrier",
                        "The immediately preceding governed gate must close before this activity starts.",
                    )

            version.write({"dependency_review_status": "unreviewed"})
        return True
