"""Reconcile gate scope to Checklist Model Specification v2."""


MOULD_STAGE_CODES = ("TG-02", "TG-03", "TG-04", "TG-05", "TG-06", "TG-07", "TG-08", "TG-09")


def migrate(cr, version):
    cr.execute(
        """
        UPDATE hjig_programme_template_gate AS gate
           SET execution_basis = CASE
               WHEN stage.code = ANY(%s) THEN 'mould'
               ELSE 'project'
           END
          FROM hjig_launchguard_stage AS stage
         WHERE gate.stage_id = stage.id
        """,
        (list(MOULD_STAGE_CODES),),
    )
