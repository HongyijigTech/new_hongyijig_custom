"""Reconcile evidence applicability to the authoritative Drive gate routes."""


def _xmlid_res_id(cr, name):
    cr.execute(
        """
        SELECT res_id FROM ir_model_data
         WHERE module = 'new_hongyijig_custom' AND name = %s
        """,
        [name],
    )
    row = cr.fetchone()
    if not row:
        raise RuntimeError("Missing required XML ID new_hongyijig_custom.%s" % name)
    return row[0]


def migrate(cr, version):
    additions = {
        "artifact_sop_002": ("stage_pa00", "stage_lgd_signoff", "stage_pre_b2"),
        "artifact_sop_003": ("stage_lgd_signoff",),
        "artifact_sop_004": ("stage_pa00", "stage_lgd_signoff", "stage_pre_b2"),
        "artifact_frm_003": ("stage_pa00", "stage_lgd_signoff", "stage_pre_b2"),
        "artifact_frm_004": ("stage_pa00", "stage_lgd_signoff", "stage_pre_b2"),
        "artifact_frm_005": ("stage_pa00", "stage_lgd_signoff", "stage_pre_b2"),
        "artifact_frm_006": (
            "stage_pa00", "stage_lgd_signoff", "stage_pre_b2",
            "stage_tg10", "stage_tg10_lite",
        ),
        "artifact_frm_007": ("stage_tg01", "stage_pre_b2"),
        "artifact_frm_023": ("stage_tg10", "stage_tg10_lite"),
        "artifact_frm_024": ("stage_lgd_signoff", "stage_pre_b2"),
        "artifact_frm_027": ("stage_lgd_signoff",),
    }
    for artifact_xmlid, stage_xmlids in additions.items():
        artifact_id = _xmlid_res_id(cr, artifact_xmlid)
        for stage_xmlid in stage_xmlids:
            stage_id = _xmlid_res_id(cr, stage_xmlid)
            cr.execute(
                """
                INSERT INTO hjig_artifact_stage_rel (artifact_id, stage_id)
                SELECT %s, %s
                 WHERE NOT EXISTS (
                    SELECT 1 FROM hjig_artifact_stage_rel
                     WHERE artifact_id = %s AND stage_id = %s
                 )
                """,
                [artifact_id, stage_id, artifact_id, stage_id],
            )
