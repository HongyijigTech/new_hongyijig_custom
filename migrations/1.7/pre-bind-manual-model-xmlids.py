"""Bind existing production manual models to stable module XML IDs."""


def migrate(cr, version):
    for model_name in ("x_mould", "x_mould_part"):
        xmlid_name = "model_%s" % model_name.replace(".", "_")
        cr.execute(
            """
            INSERT INTO ir_model_data
                (module, name, model, res_id, noupdate, create_uid, write_uid, create_date, write_date)
            SELECT
                'new_hongyijig_custom', %s, 'ir.model', model.id, TRUE, 1, 1, NOW(), NOW()
            FROM ir_model AS model
            WHERE model.model = %s
              AND NOT EXISTS (
                  SELECT 1
                  FROM ir_model_data AS data
                  WHERE data.module = 'new_hongyijig_custom'
                    AND data.name = %s
              )
            """,
            (xmlid_name, model_name, xmlid_name),
        )
