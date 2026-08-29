"""Run with ``odoo-bin shell`` before upgrading an existing production database.

This changes only the ir.model ownership marker for the two existing mould
tables. Record tables, IDs and business values are not rewritten.
"""
import json


model_names = ("x_mould", "x_mould_part")
models = env["ir.model"].search([("model", "in", model_names)])
found = set(models.mapped("model"))
unexpected = found - set(model_names)
if unexpected:
    raise RuntimeError("Unexpected model selection: %s" % sorted(unexpected))

before = {
    item.model: {
        "ir_model_id": item.id,
        "state": item.state,
        "record_count": env[item.model].with_context(active_test=False).search_count([]),
    }
    for item in models
}
env.cr.execute(
    "UPDATE ir_model SET state = 'base' WHERE model IN %s AND state = 'manual'",
    (model_names,),
)
promoted_rows = env.cr.rowcount
env.cr.commit()

after = {
    item.model: env["ir.model"].browse(item.id).state
    for item in models
}
print("HJIG_LEGACY_MODEL_PROMOTION=" + json.dumps({
    "before": before,
    "after": after,
    "promoted_rows": promoted_rows,
}, sort_keys=True))
