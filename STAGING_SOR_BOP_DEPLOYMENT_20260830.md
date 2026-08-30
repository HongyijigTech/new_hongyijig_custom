# SOR and BOP Controls — Staging Deployment Report

Date: 30 August 2026 (IST)

## Scope

- Environment changed: staging only (`HongyijigTech_10Feb`, port 8070)
- Production service and database: unchanged
- Programme versions: retained as draft/unreviewed
- Programme runs created: 0
- Existing mould-planning, BOP workbook, risk, issue/design-challenge, ECN and inspection carriers: retained; no duplicate models created

## Release identity

- Branch: `feature/wp001-sor-bop`
- Commit: `45a8c568166da5d7d4a3acc2c45943f5e8cd2024`
- Module version: `19.0.3.6.0`
- Release archive: `Hongyi_Odoo_WP001_45a8c56.tar.gz`
- SHA-256: `ce2b37b835320eb4c02ae3eb54be7895e03875b74403976db37fc77bad4dca93`

## Implemented controls

- Route A continues to map a customer-owned SOR with mandatory source traceability.
- Route B now loads the controlled Automotive or MED/CE/HA guided template.
- Automotive loads 22 sectioned requirement groups.
- MED/CE/HA loads 36 sectioned requirement groups and only the selected domain declaration.
- Requirement groups are automatically allocated to applicable lifecycle phases.
- Guided requirements capture customer declaration, acceptance criteria, owner, clarification date and evidence plan.
- MED/CE/HA issuance requires approved Order Punch confirmation.
- Engineering responsibility is explicitly Option A, B or C; Option C requires a written HJIG scope.
- Guided SOR review requires customer sign-off identity, designation and date.
- No-HJIG-product-warranty boundary remains enforced.
- BOP remains the controlled `FRM-004 BOP Lock Record`; only readiness summary and approval controls were added to its document header.
- BOP approval blocks Pending and Envelope-only items and requires Frozen items, customer freeze confirmation and lock date.

## Verification

- Python compilation: PASS
- XML parsing: PASS
- Git whitespace validation: PASS
- Disposable staging-clone module upgrade: PASS
- Module regression: 144 tests, 0 failures, 0 errors
- Programme-authority validation: PASS
- Post-deployment SOR/BOP field validation: `STAGING_SOR_BOP_CONTROLS_PASS fields=20 programme_runs=0`
- Staging HTTP: 200
- Staging service: active
- Production service: active
- Browser UAT: SOR Register and new guided SOR form render without browser warnings/errors

## Recovery evidence

- Pre-deployment rollback directory: `/home/hongyi-jig-erp/releases/rollback/45a8c56_predeploy_20260830_083427`
- Database, filestore, configuration, service definition and previous module were backed up and checksum-verified before the staging service was stopped.
- Automatic rollback remained armed through the database upgrade and post-deployment validations.

## Source documents

- Automotive SOR: `HONGYI MASTER AUTOMOTIVE SOR`
- MED/CE/HA SOR: `SOR-MED-CE-HA-v2.1`
- Both source documents were read directly from the approved Google Drive files before implementation.
