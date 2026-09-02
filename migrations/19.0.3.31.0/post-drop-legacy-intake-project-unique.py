"""Remove the pre-supersession one-case-per-intake-project database constraint."""


def migrate(cr, version):
    # Supersession retains the original intake project and is now protected by
    # active_intake_project_key.  The old physical UNIQUE(intake_project_id)
    # constraint blocks that governed successor relation.
    cr.execute(
        "ALTER TABLE hjig_sseries_case "
        "DROP CONSTRAINT IF EXISTS hjig_sseries_case_intake_project_case_unique"
    )
