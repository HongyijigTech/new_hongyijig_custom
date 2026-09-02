from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Repair legacy finish snapshots and recompute employee readiness scores."""
    cr.execute(
        """
        UPDATE x_mould_part AS part
           SET x_surface_finish_type = finish.finish_system,
               x_surface_grade_code = finish.code,
               x_surface_details = CONCAT_WS(
                   E'\n',
                   NULLIF(finish.name, ''),
                   NULLIF(finish.method, ''),
                   NULLIF(finish.appearance, ''),
                   NULLIF(finish.roughness_or_depth, ''),
                   NULLIF(finish.tooling_notes, '')
               )
          FROM hjig_surface_finish_master AS finish
         WHERE part.x_surface_finish_id = finish.id
           AND (
               part.x_surface_finish_type IS DISTINCT FROM finish.finish_system
               OR part.x_surface_grade_code IS DISTINCT FROM finish.code
           )
        """
    )
    cr.execute(
        """
        UPDATE x_mould_part AS part
           SET x_surface_grade_code = NULL,
               x_surface_details = NULL
         WHERE part.x_surface_finish_id IS NULL
           AND part.x_surface_grade_code IS NOT NULL
           AND EXISTS (
               SELECT 1
                 FROM hjig_surface_finish_master AS finish
                WHERE finish.code = part.x_surface_grade_code
                  AND finish.finish_system IS DISTINCT FROM part.x_surface_finish_type
           )
        """
    )

    env = api.Environment(cr, SUPERUSER_ID, {})
    migration_context = {
        "active_test": False,
        "allow_mould_lifecycle_control": True,
        "tracking_disable": True,
    }
    parts = env["x_mould_part"].with_context(**migration_context).search([])
    for offset in range(0, len(parts), 500):
        parts[offset:offset + 500]._compute_completeness()
    moulds = env["x_mould"].with_context(**migration_context).search([])
    for offset in range(0, len(moulds), 500):
        moulds[offset:offset + 500]._compute_part_summary()
