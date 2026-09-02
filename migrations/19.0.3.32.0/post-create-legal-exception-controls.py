"""Backfill the two manual legal-exception controls for existing S-Series cases."""


def migrate(cr, version):
    for exception_type in ("introduced_party_notice", "direct_engagement_consent"):
        cr.execute(
            "INSERT INTO hjig_sseries_legal_exception "
            "(case_id, exception_type, applicable, legal_approved, create_uid, create_date, write_uid, write_date) "
            "SELECT c.id, %s, 'not_set', FALSE, 1, NOW(), 1, NOW() "
            "FROM hjig_sseries_case c "
            "WHERE NOT EXISTS ("
            "SELECT 1 FROM hjig_sseries_legal_exception e "
            "WHERE e.case_id = c.id AND e.exception_type = %s"
            ")",
            (exception_type, exception_type),
        )
