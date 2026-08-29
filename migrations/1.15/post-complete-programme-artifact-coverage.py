"""Complete mandatory artifact coverage for PRE-B2 and closure routes.

Existing master records are noupdate, so their additional stage links must be
reconciled explicitly during upgrade. New SOP-014 and FRM-043 records are loaded
normally from XML before this post-migration runs.
"""


def _xmlid_res_id(cr, name):
    cr.execute(
        """
        SELECT res_id
          FROM ir_model_data
         WHERE module = 'new_hongyijig_custom'
           AND name = %s
        """,
        [name],
    )
    row = cr.fetchone()
    if not row:
        raise RuntimeError("Missing required XML ID new_hongyijig_custom.%s" % name)
    return row[0]


def migrate(cr, version):
    stage_pre_b2 = _xmlid_res_id(cr, "stage_pre_b2")
    for artifact_xmlid in ("artifact_sop_005", "artifact_frm_028", "artifact_frm_029"):
        artifact_id = _xmlid_res_id(cr, artifact_xmlid)
        cr.execute(
            """
            INSERT INTO hjig_artifact_stage_rel (artifact_id, stage_id)
            SELECT %s, %s
             WHERE NOT EXISTS (
                 SELECT 1 FROM hjig_artifact_stage_rel
                  WHERE artifact_id = %s AND stage_id = %s
             )
            """,
            [artifact_id, stage_pre_b2, artifact_id, stage_pre_b2],
        )
