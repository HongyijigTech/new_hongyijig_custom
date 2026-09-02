def migrate(cr, version):
    """Remove legacy finish snapshots that contradict the selected finish system."""
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
