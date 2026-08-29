"""Reconcile the installed 10-stage master with the verified programme routes.

The data file is noupdate so existing PA-00/TG-09 records are corrected once here.
New PRE-B2, TG-10, TG-10-LITE and ToolLock Lite session records are created by XML.
"""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE hjig_launchguard_stage
           SET legacy_code = 'IG-01', write_date = NOW(), write_uid = 1
         WHERE code = 'PA-00'
           AND COALESCE(legacy_code, '') != 'IG-01'
        """
    )
    cr.execute(
        """
        UPDATE hjig_launchguard_stage
           SET stage_type = 'technical_gate', write_date = NOW(), write_uid = 1
         WHERE code = 'TG-09'
           AND stage_type = 'closure'
        """
    )
