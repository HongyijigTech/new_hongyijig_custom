"""Bind the existing live CRM spine stages before loading governed XML records."""


STAGES = {
    "crm_stage_hjig_pre_fd": "Pre-FD",
    "crm_stage_hjig_fd_series": "FD-Series",
    "crm_stage_hjig_p_series": "P-Series",
    "crm_stage_hjig_s_series": "S-Series",
    "crm_stage_hjig_order_punch": "Order Punch",
    "crm_stage_hjig_bseries_handover": "B-Series Handover",
}


def migrate(cr, version):
    for xmlid_name, stage_name in STAGES.items():
        cr.execute(
            """
            SELECT id
              FROM crm_stage
             WHERE COALESCE(name->>'en_US', name->>'en_IN') = %s
          ORDER BY id
             LIMIT 1
            """,
            (stage_name,),
        )
        row = cr.fetchone()
        if not row:
            continue
        cr.execute(
            """
            INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
                 VALUES ('new_hongyijig_custom', %s, 'crm.stage', %s, TRUE)
            ON CONFLICT (module, name) DO NOTHING
            """,
            (xmlid_name, row[0]),
        )
