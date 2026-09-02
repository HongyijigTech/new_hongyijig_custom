"""Make the active S-Series intake-key handoff atomic within one transaction."""


def migrate(cr, version):
    # The exact current physical constraint name is confirmed by the clone
    # error: hjig_sseries_case_active_intake_project_case_unique.  Successor
    # creation relinquishes then claims the key inside one transaction.
    cr.execute(
        "ALTER TABLE hjig_sseries_case "
        "DROP CONSTRAINT IF EXISTS hjig_sseries_case_active_intake_project_case_unique"
    )
    cr.execute(
        "ALTER TABLE hjig_sseries_case "
        "ADD CONSTRAINT hjig_sseries_case_active_intake_project_case_unique "
        "UNIQUE (active_intake_project_key) DEFERRABLE INITIALLY DEFERRED"
    )
