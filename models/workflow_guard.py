# -*- coding: utf-8 -*-

# A JSON/RPC caller can forge ordinary context booleans. This in-process object
# identity cannot be reconstructed by a remote client, so only server-side
# workflow methods can obtain the guarded write path.
WORKFLOW_CONTEXT_KEY = "_hjig_internal_workflow_token"
WORKFLOW_TOKEN = object()


def staging_self_approval_demo_enabled(env):
    """Permit an audited same-user walkthrough only on the explicitly named DB."""
    parameters = env["ir.config_parameter"].sudo()
    enabled = parameters.get_param(
        "new_hongyijig_custom.staging_self_approval_demo", "0"
    ) == "1"
    configured_database = parameters.get_param(
        "new_hongyijig_custom.staging_self_approval_database", ""
    )
    return enabled and configured_database == env.cr.dbname


def record_staging_demo_transition(record, from_state, to_state, decision):
    """Make every training-only maker/checker bypass visible in audit history."""
    record.ensure_one()
    project = (
        record.project_id
        if "project_id" in record._fields
        else record.x_project_id
    )
    record.env["hjig.transition.log"].sudo().create({
        "project_id": project.id,
        "target_ref": "%s,%s" % (record._name, record.id),
        "from_state": from_state,
        "to_state": to_state,
        "decision": decision,
        "actor_id": record.env.user.id,
        "reason": (
            "STAGING TRAINING OVERRIDE: the single licensed staging user "
            "performed both maker and checker steps for this demonstration."
        ),
    })


def workflow_context():
    return {WORKFLOW_CONTEXT_KEY: WORKFLOW_TOKEN}


def is_workflow_context(env):
    return env.context.get(WORKFLOW_CONTEXT_KEY) is WORKFLOW_TOKEN
