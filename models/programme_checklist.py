# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class HjigProgrammeTemplateChecklistItem(models.Model):
    _name = "hjig.programme.template.checklist.item"
    _description = "Programme Gate Checklist Template Item"
    _inherit = "hjig.programme.version.child.mixin"
    _order = "gate_line_id, sequence, code"

    version_id = fields.Many2one(
        "hjig.programme.template.version", required=True, ondelete="cascade", index=True
    )
    gate_line_id = fields.Many2one(
        "hjig.programme.template.gate", required=True, ondelete="cascade", index=True
    )
    code = fields.Char(required=True, index=True)
    sequence = fields.Integer(required=True, default=10)
    subhead = fields.Selection(
        [
            ("technical", "Technical"),
            ("commercial", "Commercial"),
            ("reporting", "Reporting"),
            ("governance", "Governance"),
            ("customer", "Customer"),
            ("supplier", "Supplier"),
        ],
        required=True,
    )
    item_text = fields.Text(required=True)
    mandatory = fields.Boolean(default=True)
    conditional = fields.Boolean(default=False)
    evidence_required = fields.Boolean(default=True)
    sign_required = fields.Boolean(
        default=False,
        help="A Pass requires an approved controlled signed-document record.",
    )
    execution_basis = fields.Selection(
        [("project", "Project"), ("mould", "Mould")], required=True, default="project"
    )
    linked_activity_id = fields.Many2one(
        "hjig.programme.template.activity", ondelete="restrict", index=True
    )
    evidence_artifact_id = fields.Many2one(
        "hjig.governance.artifact.master", ondelete="restrict"
    )
    owner_designation_id = fields.Many2one(
        "hjig.governance.designation", required=True, ondelete="restrict"
    )
    approver_designation_id = fields.Many2one(
        "hjig.governance.designation", required=True, ondelete="restrict"
    )
    auto_na_risk_below = fields.Integer(
        help="When set, this conditional item is automatically N/A if the project has no unresolved risk at or above this score."
    )
    source_reference = fields.Char(required=True)
    source_version = fields.Char(required=True)

    _version_code_unique = models.Constraint(
        "UNIQUE(version_id, code)",
        "Checklist item code must be unique within a programme version.",
    )

    @api.constrains(
        "version_id", "gate_line_id", "linked_activity_id", "execution_basis",
        "conditional", "auto_na_risk_below", "owner_designation_id", "approver_designation_id",
    )
    def _check_template_item(self):
        for item in self:
            if item.gate_line_id.version_id != item.version_id:
                raise ValidationError(_("The checklist gate must belong to the same programme version."))
            if item.linked_activity_id and item.linked_activity_id.version_id != item.version_id:
                raise ValidationError(_("The linked activity must belong to the same programme version."))
            if item.execution_basis == "mould" and item.gate_line_id.execution_basis != "mould":
                raise ValidationError(_("A mould-basis checklist item requires a mould-basis gate."))
            if item.auto_na_risk_below and not item.conditional:
                raise ValidationError(_("Automatic N/A logic is allowed only on conditional items."))
            if item.owner_designation_id == item.approver_designation_id:
                raise ValidationError(_("Checklist owner and approver designations must be different."))


class HjigProgrammeChecklistInstance(models.Model):
    _name = "hjig.programme.checklist.instance"
    _description = "Live Programme Gate Checklist Item"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "run_gate_id, template_item_id"

    run_id = fields.Many2one(
        "hjig.programme.run", required=True, ondelete="cascade", index=True, readonly=True
    )
    run_gate_id = fields.Many2one(
        "hjig.programme.run.gate", ondelete="cascade", index=True, readonly=True
    )
    template_item_id = fields.Many2one(
        "hjig.programme.template.checklist.item",
        required=True,
        ondelete="restrict",
        index=True,
        readonly=True,
    )
    project_id = fields.Many2one(
        related="run_id.project_id", store=True, readonly=True, index=True
    )
    mould_id = fields.Many2one(
        "x_mould", ondelete="restrict", index=True, readonly=True
    )
    code = fields.Char(related="template_item_id.code", store=True, readonly=True)
    item_text = fields.Text(related="template_item_id.item_text", readonly=True)
    subhead = fields.Selection(related="template_item_id.subhead", store=True, readonly=True)
    mandatory = fields.Boolean(related="template_item_id.mandatory", store=True, readonly=True)
    conditional = fields.Boolean(related="template_item_id.conditional", store=True, readonly=True)
    evidence_required = fields.Boolean(
        related="template_item_id.evidence_required", store=True, readonly=True
    )
    sign_required = fields.Boolean(
        related="template_item_id.sign_required", store=True, readonly=True
    )
    owner_designation_id = fields.Many2one(
        related="template_item_id.owner_designation_id", store=True, readonly=True
    )
    approver_designation_id = fields.Many2one(
        related="template_item_id.approver_designation_id", store=True, readonly=True
    )
    status = fields.Selection(
        [("pending", "Pending"), ("pass", "Pass"), ("fail", "Fail"), ("na", "N/A")],
        required=True,
        default="pending",
        tracking=True,
    )
    evidence_document_id = fields.Many2one(
        "hjig.project.document", ondelete="restrict", tracking=True
    )
    remarks = fields.Text(tracking=True)
    ticked_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    ticked_on = fields.Datetime(readonly=True, copy=False)
    disposition_approved_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    disposition_approved_on = fields.Datetime(readonly=True, copy=False)
    automatic_disposition = fields.Boolean(readonly=True, copy=False)

    _run_item_mould_unique = models.Constraint(
        "UNIQUE(run_id, template_item_id, mould_id)",
        "A checklist template item may have only one live instance per project or mould.",
    )

    @api.constrains("run_id", "run_gate_id", "template_item_id", "mould_id", "evidence_document_id")
    def _check_instance_scope(self):
        for item in self:
            if item.run_gate_id and item.run_gate_id.run_id != item.run_id:
                raise ValidationError(_("The checklist gate must belong to the same programme run."))
            if item.run_gate_id and item.run_gate_id.template_gate_id != item.template_item_id.gate_line_id:
                raise ValidationError(_("The checklist item does not belong to this gate."))
            if item.template_item_id.execution_basis == "mould":
                if not item.mould_id or not item.run_gate_id or item.mould_id != item.run_gate_id.mould_id:
                    raise ValidationError(_("A mould-basis checklist item requires the matching mould gate."))
            elif item.mould_id:
                raise ValidationError(_("A project-basis checklist item cannot carry a mould."))
            if item.mould_id and item.mould_id.x_project_id != item.project_id:
                raise ValidationError(_("The checklist mould must belong to the programme project."))
            duplicate = self.search_count([
                ("run_id", "=", item.run_id.id),
                ("template_item_id", "=", item.template_item_id.id),
                ("mould_id", "=", item.mould_id.id if item.mould_id else False),
                ("id", "!=", item.id),
            ])
            if duplicate:
                raise ValidationError(_("A checklist item can appear only once in the same project or mould scope."))
            document = item.evidence_document_id
            if document:
                if document.project_id != item.project_id or document.stage_id != item.template_item_id.gate_line_id.stage_id:
                    raise ValidationError(_("Checklist evidence must belong to the same project and gate."))
                if document.mould_id != item.mould_id:
                    raise ValidationError(_("Checklist evidence must use the same mould scope."))
                required_artifact = item.template_item_id.evidence_artifact_id
                if required_artifact and document.artifact_master_id != required_artifact:
                    raise ValidationError(_("Checklist evidence uses the wrong governed SOP/Form type."))

    def _assert_open(self):
        for item in self:
            gates = item.run_gate_id or item.run_id.gate_ids.filtered(
                lambda gate: gate.template_gate_id == item.template_item_id.gate_line_id
            )
            if gates.filtered(lambda gate: gate.state == "approved"):
                raise ValidationError(_("Checklist items are immutable after gate approval."))

    def _assert_owner(self):
        for item in self:
            if self.env.user not in item.owner_designation_id.holder_ids:
                raise UserError(_("Only a current holder of the checklist Owner Designation may record this result."))

    def action_mark_pass(self):
        self._assert_open()
        self._assert_owner()
        for item in self:
            if item.evidence_required and (
                not item.evidence_document_id or item.evidence_document_id.status != "approved"
            ):
                raise ValidationError(_("Approved controlled evidence is required before recording Pass."))
            item.with_context(hjig_checklist_workflow=True).write({
                "status": "pass",
                "ticked_by_id": self.env.user.id,
                "ticked_on": fields.Datetime.now(),
                "automatic_disposition": False,
                "disposition_approved_by_id": False,
                "disposition_approved_on": False,
            })
        return True

    def action_mark_fail(self):
        self._assert_open()
        self._assert_owner()
        for item in self:
            if not (item.remarks or "").strip():
                raise ValidationError(_("Remarks are mandatory when recording Fail."))
            item.with_context(hjig_checklist_workflow=True).write({
                "status": "fail",
                "ticked_by_id": self.env.user.id,
                "ticked_on": fields.Datetime.now(),
                "automatic_disposition": False,
                "disposition_approved_by_id": False,
                "disposition_approved_on": False,
            })
        return True

    def action_mark_na(self):
        self._assert_open()
        for item in self:
            if not item.conditional:
                raise ValidationError(_("Only a conditional checklist item may be marked N/A."))
            if self.env.user not in item.approver_designation_id.holder_ids:
                raise UserError(_("Only a current holder of the Approver Designation may approve N/A."))
            if not (item.remarks or "").strip():
                raise ValidationError(_("A controlled N/A disposition requires remarks."))
            item.with_context(hjig_checklist_workflow=True).write({
                "status": "na",
                "ticked_by_id": self.env.user.id,
                "ticked_on": fields.Datetime.now(),
                "disposition_approved_by_id": self.env.user.id,
                "disposition_approved_on": fields.Datetime.now(),
                "automatic_disposition": False,
            })
        return True

    def write(self, vals):
        self._assert_open()
        identity = {"run_id", "run_gate_id", "template_item_id", "mould_id"}
        if identity.intersection(vals):
            raise ValidationError(_("Generated checklist identity is immutable."))
        workflow = {
            "status", "ticked_by_id", "ticked_on", "disposition_approved_by_id",
            "disposition_approved_on", "automatic_disposition",
        }
        if workflow.intersection(vals) and not self.env.context.get("hjig_checklist_workflow"):
            raise ValidationError(_("Use the governed checklist actions to record a result."))
        return super().write(vals)

    def unlink(self):
        raise UserError(_("Generated checklist instances cannot be deleted."))
