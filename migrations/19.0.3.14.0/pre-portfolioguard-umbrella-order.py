"""Permit multiple child programme runs only under one PortfolioGuard umbrella order."""


def migrate(cr, version):
    cr.execute(
        "ALTER TABLE hjig_programme_run "
        "DROP CONSTRAINT IF EXISTS hjig_programme_run_sale_order_unique"
    )
