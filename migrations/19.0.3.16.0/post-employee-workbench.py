def migrate(cr, version):
    """Apply the employee-facing IG label when upgrading from active staging 3.15."""
    cr.execute(
        """
        UPDATE hjig_launchguard_stage
           SET name = 'IG-01 — Information & Planning Gate',
               legacy_code = 'IG-01',
               write_date = NOW(),
               write_uid = 1
         WHERE code = 'PA-00'
           AND (name IS DISTINCT FROM 'IG-01 — Information & Planning Gate'
                OR legacy_code IS DISTINCT FROM 'IG-01')
        """
    )
