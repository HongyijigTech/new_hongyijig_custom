# -*- coding: utf-8 -*-

# A JSON/RPC caller can forge ordinary context booleans. This in-process object
# identity cannot be reconstructed by a remote client, so only server-side
# workflow methods can obtain the guarded write path.
WORKFLOW_CONTEXT_KEY = "_hjig_internal_workflow_token"
WORKFLOW_TOKEN = object()


def workflow_context():
    return {WORKFLOW_CONTEXT_KEY: WORKFLOW_TOKEN}


def is_workflow_context(env):
    return env.context.get(WORKFLOW_CONTEXT_KEY) is WORKFLOW_TOKEN
