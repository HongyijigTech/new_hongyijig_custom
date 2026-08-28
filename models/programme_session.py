# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


SESSION_CODES = tuple("TLL-S%02d" % number for number in range(1, 7))


class HjigProgrammeTemplate(models.Model):
    _inherit = "hjig.programme.template"

    execution_mode = fields.Selection(
        [
            ("governed_gates", "Governed Gates and Activities"),
            ("advisory_sessions", "Advisory Sessions"),
        ],
        required=True,
        default="governed_gates",
        tracking=True,
        help="ToolLock Lite is session-based and must not generate B-Series gates or activities.",
    )

    def write(self, vals):
        if "execution_mode" in vals and self.version_ids.filtered(
            lambda version: version.state == "approved"
        ):
            raise ValidationError(
                _("Execution mode cannot be changed after a programme version is approved.")
            )
        return super().write(vals)


class HjigProgrammeTemplateVersion(models.Model):
    _inherit = "hjig.programme.template.version"

    execution_mode = fields.Selection(
        related="template_id.execution_mode", store=True, readonly=True
    )
    session_line_ids = fields.One2many(
        "hjig.programme.template.session", "version_id", string="Advisory Session Template"
    )

    def write(self, vals):
        if "session_line_ids" in vals:
            self._assert_mutable()
        return super().write(vals)

    def _validate_definition(self):
        governed = self.filtered(lambda version: version.execution_mode == "governed_gates")
        if governed:
            super(HjigProgrammeTemplateVersion, governed)._validate_definition()
        for version in self - governed:
            if version.template_id.code != "TLL":
                raise ValidationError(_("Only ToolLock Lite may use advisory-session execution."))
            if version.gate_line_ids or version.activity_line_ids or version.dependency_rule_ids:
                raise ValidationError(
                    _("An advisory programme cannot contain B-Series gates, activities, or dependencies.")
                )
            if version.artifact_rule_ids or version.checklist_item_ids:
                raise ValidationError(
                    _("Advisory session evidence belongs on the session template, not gate controls.")
                )
            sessions = version.session_line_ids.sorted("sequence")
            if tuple(sessions.mapped("code")) != SESSION_CODES:
                raise ValidationError(_("ToolLock Lite requires exactly the six controlled sessions TLL-S01 to TLL-S06."))
            if version.legacy_source_task_count and sum(sessions.mapped("source_task_count")) != version.legacy_source_task_count:
                raise ValidationError(
                    _("Advisory-session source counts must reconcile to the verified legacy task count.")
                )
            if sessions.filtered(lambda item: not item.framework_artifact_id):
                raise ValidationError(_("Every advisory session requires one controlled blank framework."))
            if version.dependency_review_status != "verified":
                raise ValidationError(_("The advisory-session sequence must be verified before review."))
            if version.evidence_review_status != "verified":
                raise ValidationError(_("The advisory framework map must be verified before review."))

    def _definition_payload(self):
        self.ensure_one()
        if self.execution_mode == "governed_gates":
            payload = super()._definition_payload()
            payload["execution_mode"] = self.execution_mode
            return payload
        return {
            "programme": self.template_id.code,
            "version": self.version,
            "effective_from": fields.Date.to_string(self.effective_from),
            "execution_mode": self.execution_mode,
            "legacy_source": {
                "database": self.legacy_source_database,
                "project_id": self.legacy_source_project_id,
                "task_count": self.legacy_source_task_count,
            },
            "sessions": [session._snapshot_values() for session in self.session_line_ids.sorted("sequence")],
            "dependency_review_status": self.dependency_review_status,
            "evidence_review_status": self.evidence_review_status,
        }


class HjigProgrammeTemplateSession(models.Model):
    _name = "hjig.programme.template.session"
    _description = "Programme Advisory Session Template"
    _inherit = "hjig.programme.version.child.mixin"
    _order = "version_id, sequence, id"

    version_id = fields.Many2one(
        "hjig.programme.template.version", required=True, ondelete="cascade", index=True
    )
    code = fields.Char(required=True, index=True)
    sequence = fields.Integer(required=True)
    name = fields.Char(required=True)
    indicative_duration = fields.Char(required=True)
    stage_id = fields.Many2one(
        "hjig.launchguard.stage", required=True, ondelete="restrict", index=True
    )
    owner_designation_id = fields.Many2one(
        "hjig.governance.designation", required=True, ondelete="restrict"
    )
    approver_designation_id = fields.Many2one(
        "hjig.governance.designation", required=True, ondelete="restrict"
    )
    framework_artifact_id = fields.Many2one(
        "hjig.governance.artifact.master", required=True, ondelete="restrict"
    )
    legacy_source_task_ids = fields.Char(required=True, readonly=True, copy=False)
    source_task_count = fields.Integer(required=True, default=2, readonly=True, copy=False)
    source_reference = fields.Char(required=True)
    source_version = fields.Char(required=True)
    advisory_scope = fields.Text(
        required=True,
        default="Advisory review using a blank controlled framework; tooling execution remains outside scope.",
    )

    _version_code_unique = models.Constraint(
        "UNIQUE(version_id, code)", "Advisory session code must be unique in a programme version."
    )
    _version_sequence_unique = models.Constraint(
        "UNIQUE(version_id, sequence)", "Advisory session sequence must be unique in a programme version."
    )

    @api.constrains(
        "version_id", "code", "owner_designation_id", "approver_designation_id",
        "stage_id", "framework_artifact_id", "source_task_count",
    )
    def _check_session_governance(self):
        for session in self:
            if session.version_id.execution_mode != "advisory_sessions":
                raise ValidationError(_("Advisory sessions require an advisory-session programme."))
            if session.owner_designation_id == session.approver_designation_id:
                raise ValidationError(_("Session owner and approver designations must be different."))
            if session.source_task_count <= 0:
                raise ValidationError(_("Session source-task count must be positive."))
            if session.framework_artifact_id.artifact_type != "form":
                raise ValidationError(_("The advisory framework must be a governed form master."))
            if session.stage_id.code != session.code:
                raise ValidationError(_("The advisory session must use its matching controlled stage."))
            if session.stage_id not in session.framework_artifact_id.applicable_stage_ids:
                raise ValidationError(_("The advisory framework is not approved for this session stage."))

    def _snapshot_values(self):
        self.ensure_one()
        return {
            "code": self.code,
            "sequence": self.sequence,
            "name": self.name,
            "indicative_duration": self.indicative_duration,
            "stage": self.stage_id.code,
            "owner": self.owner_designation_id.code,
            "approver": self.approver_designation_id.code,
            "framework": self.framework_artifact_id.code,
            "legacy_source_task_ids": self.legacy_source_task_ids,
            "source_task_count": self.source_task_count,
            "source_reference": self.source_reference,
            "source_version": self.source_version,
            "advisory_scope": self.advisory_scope,
        }


class HjigProgrammeRun(models.Model):
    _inherit = "hjig.programme.run"

    execution_mode = fields.Selection(
        related="template_version_id.execution_mode", store=True, readonly=True
    )
    session_ids = fields.One2many(
        "hjig.programme.run.session", "run_id", string="ToolLock Lite Sessions", readonly=True
    )

    def action_generate_execution(self):
        governed = self.filtered(lambda run: run.execution_mode == "governed_gates")
        if governed:
            super(HjigProgrammeRun, governed).action_generate_execution()
        for run in self - governed:
            if run.state == "generated":
                continue
            version = run.template_version_id
            if version.state != "approved":
                raise ValidationError(_("Only an approved programme version can generate execution records."))
            version._validate_definition()
            for template_session in version.session_line_ids.sorted("sequence"):
                self.env["hjig.programme.run.session"].create({
                    "run_id": run.id,
                    "template_session_id": template_session.id,
                    "sequence": template_session.sequence,
                })
            payload = version._definition_payload()
            run.with_context(hjig_run_workflow=True).write({
                "state": "generated",
                "activated_on": fields.Datetime.now(),
                "activated_by_id": self.env.user.id,
                "definition_hash": version.definition_hash,
                "snapshot_json": payload,
            })
        return True

    def action_sync_mould_execution(self):
        if self.filtered(lambda run: run.execution_mode == "advisory_sessions"):
            raise UserError(_("Advisory-session programmes do not use mould gate execution."))
        return super().action_sync_mould_execution()

    def action_close_run(self):
        governed = self.filtered(lambda run: run.execution_mode == "governed_gates")
        if governed:
            super(HjigProgrammeRun, governed).action_close_run()
        for run in self - governed:
            if run.state != "generated":
                raise UserError(_("Only a generated programme run can be closed."))
            if len(run.session_ids) != 6 or run.session_ids.filtered(lambda item: item.state != "accepted"):
                raise ValidationError(_("All six ToolLock Lite advisory sessions must be accepted before closure."))
            run.with_context(hjig_run_workflow=True).write({"state": "closed"})
        return True


class HjigProgrammeRunSession(models.Model):
    _name = "hjig.programme.run.session"
    _description = "Programme Advisory Session Delivery"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "run_id, sequence, id"

    run_id = fields.Many2one(
        "hjig.programme.run", required=True, ondelete="cascade", index=True, readonly=True
    )
    project_id = fields.Many2one(related="run_id.project_id", store=True, readonly=True)
    template_session_id = fields.Many2one(
        "hjig.programme.template.session", required=True, ondelete="restrict", readonly=True
    )
    code = fields.Char(related="template_session_id.code", store=True, readonly=True)
    name = fields.Char(related="template_session_id.name", store=True, readonly=True)
    sequence = fields.Integer(required=True, readonly=True)
    indicative_duration = fields.Char(
        related="template_session_id.indicative_duration", readonly=True
    )
    owner_designation_id = fields.Many2one(
        related="template_session_id.owner_designation_id", readonly=True
    )
    approver_designation_id = fields.Many2one(
        related="template_session_id.approver_designation_id", readonly=True
    )
    framework_artifact_id = fields.Many2one(
        related="template_session_id.framework_artifact_id", readonly=True
    )
    stage_id = fields.Many2one(related="template_session_id.stage_id", store=True, readonly=True)
    state = fields.Selection(
        [("planned", "Planned"), ("delivered", "Delivered"), ("accepted", "Accepted")],
        required=True,
        default="planned",
        tracking=True,
    )
    delivery_mode = fields.Selection([("online", "Online"), ("offline", "Offline")], tracking=True)
    scheduled_on = fields.Datetime(tracking=True)
    delivered_on = fields.Datetime(readonly=True, copy=False, tracking=True)
    delivered_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    accepted_on = fields.Datetime(readonly=True, copy=False, tracking=True)
    accepted_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    framework_document_id = fields.Many2one(
        "hjig.project.document", string="Controlled Blank Framework", ondelete="restrict", tracking=True
    )
    delivery_note = fields.Text(tracking=True)
    acceptance_note = fields.Text(tracking=True)

    _run_template_session_unique = models.Constraint(
        "UNIQUE(run_id, template_session_id)", "An advisory session may appear only once in a programme run."
    )

    @api.constrains("run_id", "template_session_id", "framework_document_id")
    def _check_session_scope(self):
        for session in self:
            if session.template_session_id.version_id != session.run_id.template_version_id:
                raise ValidationError(_("The session template must belong to the programme-run version."))
            document = session.framework_document_id
            if document and (
                document.project_id != session.project_id
                or document.artifact_master_id != session.framework_artifact_id
                or document.stage_id != session.stage_id
            ):
                raise ValidationError(_("The controlled framework must match this project and advisory session."))

    def action_mark_delivered(self):
        for session in self:
            if session.state != "planned":
                raise UserError(_("Only a planned advisory session can be delivered."))
            if self.env.user not in session.owner_designation_id.holder_ids:
                raise UserError(_("Only a current holder of the session Owner Designation may deliver it."))
            if not session.delivery_mode or not session.framework_document_id or not session.delivery_note:
                raise ValidationError(_("Delivery mode, controlled blank framework, and delivery note are required."))
            if session.framework_document_id.status != "approved":
                raise ValidationError(_("The blank advisory framework must be approved before delivery."))
            session.with_context(hjig_session_workflow=True).write({
                "state": "delivered", "delivered_on": fields.Datetime.now(),
                "delivered_by_id": self.env.user.id,
            })
        return True

    def action_accept(self):
        for session in self:
            if session.state != "delivered":
                raise UserError(_("Only a delivered advisory session can be accepted."))
            if self.env.user not in session.approver_designation_id.holder_ids:
                raise UserError(_("Only a current holder of the session Approver Designation may accept it."))
            if not session.acceptance_note:
                raise ValidationError(_("An acceptance note is required."))
            session.with_context(hjig_session_workflow=True).write({
                "state": "accepted", "accepted_on": fields.Datetime.now(),
                "accepted_by_id": self.env.user.id,
            })
        return True

    def write(self, vals):
        frozen = {"run_id", "template_session_id", "sequence"}
        if frozen.intersection(vals):
            raise ValidationError(_("Generated advisory-session identity is immutable."))
        if "state" in vals and not self.env.context.get("hjig_session_workflow"):
            raise ValidationError(_("Use the governed session actions to change session state."))
        if self.filtered(lambda item: item.state == "accepted") and set(vals) - {"message_follower_ids"}:
            raise ValidationError(_("An accepted advisory session is immutable."))
        return super().write(vals)

    def unlink(self):
        raise UserError(_("Generated advisory sessions cannot be deleted."))
