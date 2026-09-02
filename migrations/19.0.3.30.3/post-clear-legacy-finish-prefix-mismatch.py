from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Clear legacy grade snapshots whose prefix contradicts the finish system."""
    cr.execute(
        """
        UPDATE x_mould_part
           SET x_surface_grade_code = NULL,
               x_surface_details = NULL
         WHERE x_surface_finish_id IS NULL
           AND x_surface_grade_code IS NOT NULL
           AND (
               (x_surface_finish_type = 'vdi' AND UPPER(x_surface_grade_code) LIKE 'SPI%%')
               OR (x_surface_finish_type = 'spi' AND UPPER(x_surface_grade_code) LIKE 'VDI%%')
               OR (x_surface_finish_type = 'normal' AND UPPER(x_surface_grade_code) <> 'NORMAL')
           )
        RETURNING id
        """
    )
    part_ids = [row[0] for row in cr.fetchall()]
    if not part_ids:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    context = {
        "allow_mould_lifecycle_control": True,
        "tracking_disable": True,
    }
    parts = env["x_mould_part"].with_context(**context).browse(part_ids)
    parts.invalidate_recordset()
    parts._compute_completeness()
    moulds = parts.mapped("x_mould_id").with_context(**context)
    moulds._compute_part_summary()
