def migrate(cr, version):
    cr.execute("""
        UPDATE hjig_inspection_trial_result
           SET status = CASE status
               WHEN 'open' THEN 'pending'
               WHEN 'closed' THEN 'pass'
               ELSE status
           END
         WHERE status IN ('open', 'closed')
    """)
