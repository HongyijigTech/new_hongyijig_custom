def migrate(cr, version):
    cr.execute("SELECT to_regclass('hjig_inspection_trial_result')")
    if not cr.fetchone()[0]:
        return
    cr.execute("""
        UPDATE hjig_inspection_trial_result
           SET status = CASE status
               WHEN 'open' THEN 'pending'
               WHEN 'closed' THEN 'pass'
               ELSE status
           END
         WHERE status IN ('open', 'closed')
    """)
