"""Correct legacy stage classifications for non-gate programme milestones."""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE hjig_launchguard_stage
           SET stage_type = 'milestone',
               write_date = NOW(),
               write_uid = 1
         WHERE code IN ('PRE-B2', 'LGD-SIGNOFF')
           AND stage_type IS DISTINCT FROM 'milestone'
        """
    )
