# Hongyi JIG Odoo Operating-System Design Pack

**Classification:** Hongyi Internal — Confidential  
**Business context:** ₹100 CR Revenue Plan  
**Release state:** Deployed to staging; visual UAT remains pending and production remains on HOLD
**Module:** `new_hongyijig_custom`  
**Odoo target:** 19.0  

## 1. Operating outcome

The system gives each Project one governed operating spine from customer input through installation support and closure. Employees work from the Project and its next required action. They must not re-enter facts that already exist in an authoritative operational record.

The operating pattern is:

1. Capture or attach the customer SOR.
2. Convert requirements into structured, traceable clauses.
3. Allocate every applicable requirement to one or more verification phases.
4. Freeze the approved SOR baseline.
5. Execute native Project work and existing authoritative Mould Planning, BOP, Risk, Design Challenge and ECN records.
6. Reuse those records as gate evidence; do not copy them into parallel forms.
7. Control China tooling, trials and inspections with accepted evidence.
8. Use human approvals for baselines, gates, inspections, commercial changes and knowledge.
9. Provide installation support without creating a product-warranty promise.
10. Capture approved lessons for later AI-supported retrieval.

## 2. Non-negotiable architecture decisions

| Area | Decision |
|---|---|
| Project identity | Reuse `project.project` as the cockpit and project security boundary. |
| Project planning | Reuse native Odoo Project tasks and milestones; approve baselines through `hjig.baseline`. |
| SOR | Use a structured SOR plus the original customer document. Support customer-SOR and Hongyi-guided routes. |
| Existing engineering records | Preserve the installed native forms inside `new_hongyijig_custom`, then discover and link compatible carriers at runtime. Do not create replacement Mould Planning, Part, BOP, Risk, Design Challenge or ECN registers. |
| Stage forms | Use operational records as facts and checklist/gate records as verification. A governance form is a view or evidence package, not a second data-entry system. |
| Customer/supplier ledgers | Link to native Odoo sales, purchase and accounting documents. Do not maintain duplicate financial ledgers. |
| ECN | Treat as an exception after freeze. Link engineering impact to customer commercial approval and supplier commercial cost. |
| AI | AI advises, extracts, checks and explains. It never approves, grants GO, closes an issue or changes a controlled baseline. |
| Knowledge | Only approved, effective knowledge records may be presented as Hongyi-authoritative. |
| Warranty | Hongyi provides contracted services and installation support; no product warranty is offered. |

## 3. Shared governed services

| Carrier | Purpose | Key controls |
|---|---|---|
| `project.project` | Project cockpit, programme route and authorised team | Project-scoped access; programme-specific stage visibility |
| `hjig.baseline` | Frozen revision of SOR, plan, BOP, Mould Plan or other controlled record | Human approval, supersession, immutable approved revision |
| `hjig.evidence.link` | Reusable evidence pointer | Attachment/link source, project match, independent acceptance, accepted evidence immutable |
| `hjig.approval` | Typed approval | Designation authority, no self-decision, submission snapshot/hash |
| `hjig.transition.log` | Append-only audit trail | Actor, time, from/to state, decision, reason and approval |
| `hjig.governance.designation` | Authority that survives staff changes | Approval belongs to a role designation and its current holders |
| `hjig.governance.artifact.master` | SOP/form catalogue | Owner, approver, stages, master reference and revision |

## 4. Programme routing

The selected Project programme controls which governance stages may exist.

| Programme | Allowed route |
|---|---|
| LaunchGuard Complete | PA-00 and TG-01 through TG-09 |
| LaunchGuard Design | PA-00 and TG-01 only |
| LaunchGuard Development | TG-01 through TG-09; customer design is the starting input |
| ToolLock Control | TG-01 through TG-06 and a programme-specific TG-09 Lite closure; shipment and installation stages are excluded |
| ToolLock Lite | No B-Series gates; advisory-session operation remains outside this gate route |

The server rejects an inactive gate, a gate outside the Project route, or a decision that skips the next applicable stage. Gate identity is immutable after creation; an incorrect Draft gate is recreated instead of being repurposed. A GO decision advances the Project’s last-cleared governance stage. Parallel pending decisions for the same stage are prohibited. Request, approval/rejection, cancellation and application share database transaction locks so simultaneous workers cannot produce contradictory or duplicate outcomes. A Project Manager may cancel a pending request with a recorded reason so the stage cannot become deadlocked.

The initial route is selected when the Project is created. After creation, a Project Manager can only **propose** a route change. The request requires a reason and documented commercial-impact review, creates an immutable snapshot/hash, and must be decided by the designated Governance/PMO authority before the system applies it and records a transition.

## 5. Authoritative-record connections

Runtime adapters expose an installed record only when it has a compatible Project relationship.

| Business object | Compatible authoritative carriers |
|---|---|
| Mould Planning | `x_mould`, `hjig.final.mould.plan`; other installed carriers are exposed only when they have a deterministic Project relationship |
| Mould Part / Component | `x_mould_part`; `hjig.sourcebridge.component` through its governed `engagement_id.project_id` path |
| BOP | Controlled `hjig.project.document` using `FRM-004 BOP Lock Record`, linked to the existing BOP workbook and frozen through a `bop` baseline; no duplicate BOP-line model is created |
| Risk | `hjig.project.risk`; legacy alternatives are exposed only when they have a deterministic Project relationship |
| Design Challenge / Issue | `hjig.project.issue` |
| ECN | `hjig.project.ecn` |

If a compatible carrier is absent from staging, the item is a deployment prerequisite—not permission to create a duplicate register silently.

Read-only staging registry discovery on 29 August 2026 confirmed `x_mould`, `x_mould_part`, `hjig.final.mould.plan`, `hjig.mould.register`, `hjig.project.risk`, `s.series.risk`, `hjig.project.issue`, `hjig.project.ecn` and `hjig.sourcebridge.component`. Runtime field inspection confirmed that `hjig.mould.register` and `s.series.risk` do not have a deterministic Project relationship and therefore must not be offered as governed targets; their Project-linked alternatives remain authoritative. `hjig.sourcebridge.component` is Project-resolvable through its engagement. No native BOP model was present, so the controlled-document-and-baseline route above is the required staging implementation.

Clone validation also confirmed that the authoritative Mould Planning, inspection, programme, Risk, Design Challenge, ECN and SourceBridge models are supplied by the currently installed `new_hongyijig_custom` module itself. The deployment package therefore uses a **preservation merge**: the staging 1.28 operational forms, security, data and migrations remain in the module, and the new governed foundation is added to them. A replacement-only package is prohibited because it would remove the Python registry definitions behind existing records and views.

## 6. SOR operating flow

### Route A — customer has its own SOR

1. Attach or link the original customer document and record its number/revision.
2. Extract clauses into requirement lines without changing their meaning.
3. Preserve the source clause/page reference.
4. Record acceptance criteria, ambiguity and clarification status.
5. Allocate each specified requirement to every phase where it must be checked.

### Route B — Hongyi-guided SOR

1. Use the industry-specific guided structure: automotive, medical, consumer electronics or home appliances.
2. Record requirements and acceptance criteria jointly with the customer.
3. Attach the resulting customer-approved scope evidence.

### Phase verification

A requirement may apply to design, prototype, tooling, trial, final sample, shipment, installation and/or closure. PASS or FAIL requires independently accepted evidence. A result and its evidence are locked. Re-verification requires an authorised failed-result reopen, reason and new cycle; earlier cycles remain in immutable history.

## 7. Checklists and gates

The release contains one readiness template for PA-00 and each TG-01 to TG-09. Loading a stage checklist is one click and is protected against duplicates.

Gate sequence:

1. Create the gate for an applicable Project stage and controlled target.
2. Load the single active stage template.
3. Complete every checklist response using authoritative records and accepted evidence.
4. Mark the checklist Ready.
5. Request the designated human decision.
6. Apply GO or NO-GO.
7. Close the checklist and append the decision audit trail.

AI/readiness calculations may identify missing evidence, but only the designated human approval can produce GO.

## 8. Forms and SOP delivery rule

The core operating catalogue contains 13 SOP masters and 42 form/record masters. The preservation merge retains the programme-specific and ToolLock assets already installed on staging, producing 15 SOP and 56 form/record masters in the validated clone. The workbook reference is the field/template source; the Odoo carrier determines how the employee uses it.

Three delivery types apply:

- **Native operational record:** structured Odoo model, such as SOR, China tooling report or inspection.
- **Authoritative linked record:** existing Mould Planning, BOP, Risk, Design Challenge, ECN, Project, accounting or purchase record.
- **Generated governance view/package:** a stage form that reads operational evidence and asks only for confirmation, exceptions and authority.

This rule prevents B-Series forms from duplicating Risk, trial, milestone, dispatch, installation or closure facts.

## 9. China tooling reporting

`hjig.tooling.execution` is the supplier/tool execution header linked to the authoritative Mould Plan. It supports:

- Tooling Kick-off
- Tool Manufacturing Plan
- Weekly Tooling Progress
- Milestone Completion
- Steel Verification
- Photo/Video Evidence Log
- Delay and Recovery Plan
- Supplier Action Update
- Trial Readiness
- Trial Report
- Tool Handover Dossier

Reports requiring evidence cannot enter review until that evidence is independently accepted. Submitted reports are locked throughout review. Supplier actions require accepted closure evidence and become immutable after verified closure.

## 10. Inspection structure

One shared inspection header avoids four disconnected systems. The supported types are:

- Part Visual Inspection
- Assembly Inspection
- Dimensional Inspection
- Mould Pre-Shipment Inspection

Every characteristic requires evidence. Dimensional PASS/FAIL is validated against limits, measured value, unit and instrument reference. The overall result is calculated from line results, while a human approval controls disposition.

## 11. Commercial and ECN control

`hjig.commercial.link` provides project-scoped customer and supplier views over authoritative documents or controlled external references. Commercial submission snapshots are immutable and visible only to the dedicated commercial role.

An ECN adjustment is invalid unless it links to the existing authoritative ECN. The intended chain is:

`Customer change request → ECN engineering impact → customer commercial approval → supplier cost impact → verified customer/supplier commercial links → implementation evidence`

The ECN path is exceptional; it is not part of routine project entry.

## 12. Knowledge Bank and AI coverage

Knowledge categories cover plastic material, tool steel, surface finish, runner/gate, machine capability, mould technology, tolerance/metrology, defects/CAPA, process/trials, supplier capability, lessons and SOP/templates.

Each knowledge item has a cited source, version, applicability, reviewer designation, approver designation, effectivity and lifecycle. AI provenance logs record capability, model identity, permission scope, sources, confidence, warnings, output and human disposition.

The present release supplies the governed data and provenance foundation. It does not claim that an external AI service, embeddings or automated document extraction are deployed until staging integration proves them.

## 13. Employee experience

The Project form is the entry point. Smart buttons open only Project-scoped SORs, baselines, gates, China tooling, inspections and authorised commercial records. Project Managers configure governed team membership, select the initial programme route, and propose later route changes for designated PMO approval after commercial review.

Recommended daily use:

1. Open the assigned Project.
2. Review native Project tasks/activities.
3. Open only the relevant smart button.
4. Complete the operational record or evidence request.
5. Return to the gate only when the source record is ready.

## 14. Security and separation of duties

- Every governed transactional record is limited to its authorised Project team and allowed companies.
- Commercial records require the dedicated commercial role in addition to Project membership.
- Approval authority requires the governance-approver group and the specified designation.
- A requester cannot decide their own approval.
- An evidence creator cannot accept their own evidence.
- Workflow fields use a server-only token that cannot be reproduced by an RPC context flag.
- Transition and AI provenance logs cannot be fabricated through ordinary user create/write access.

## 15. Staging deployment and verification gate

Production must remain untouched. The required path is:

1. Record the exact release commit and SHA-256 archive checksum.
2. Read-only preflight the staging service, configuration, addons path, database and currently installed module.
3. Back up staging database, filestore, configuration and active module.
4. Restore a disposable clone database.
5. Disable clone cron, outgoing mail and fetchmail.
6. Install/upgrade the preservation-merged module on the clone and execute both the retained operational-form tests and the new governed-foundation tests.
7. Run browser UAT by role and programme.
8. Upgrade the real staging database only after clone GO and an agreed maintenance window.
9. Never stop or alter `odoo-production.service`.

## 16. Minimum UAT evidence

UAT is not complete until evidence proves:

- Programme routing hides/rejects inapplicable stages for all five programme types.
- Customer-SOR and Hongyi-guided SOR routes both freeze correctly.
- One requirement can be verified at multiple phases without duplicate clauses.
- Unaccepted or self-accepted evidence cannot support PASS/FAIL.
- Rework/re-verification preserves prior-cycle evidence and result.
- A gate cannot GO without Ready checklists and an authorised human decision.
- Concurrent cancel/decide and double-apply attempts serialize to one auditable outcome.
- Existing Mould Planning, BOP, Risk, Design Challenge and ECN records are linked, not recreated.
- China weekly report, supplier action closure and all four inspection types work.
- ECN commercial links are inaccessible to non-commercial users.
- Only approved knowledge is treated as authoritative by AI support.
- No-warranty and installation-support boundaries appear at SOR and TG-09 closure.

## 17. Honest release boundary

This package is deployed to staging. Static Python/XML/CSV validation, source audit, authoritative-model discovery, the disposable-clone Odoo upgrade and the controlled real-staging upgrade are complete. The clone ran 126 post-install test methods with zero failures and zero errors, retained every required authoritative carrier, and loaded 11 readiness templates with 57 checklist items. Automated browser control of the HTTP staging URL was blocked by the organisation's browser policy, so human visual UAT remains pending; production must stay on HOLD.

## 18. Staging deployment evidence — 29 August 2026

- Functional release commit: `2ffd5fdbf3a1bf77ea01d3dd0dccdf7a56301eed`.
- Installed module/version: `new_hongyijig_custom` / `19.0.3.2.0`.
- Disposable clone: 126 post-install test methods, 0 failures, 0 errors.
- Live staging: service active from 10:50:56 IST; `/web/login` returned HTTP 303; latest 300 log lines contained 0 ERROR/CRITICAL entries.
- Live integrity: 15 SOP masters, 56 form/record masters, 11 readiness templates and 57 checklist items.
- Preserved carriers: Mould Planning, Mould Parts, legacy inspection reports, Final Mould Plans, Risk, Design Challenges, ECN and SourceBridge all remained in the Odoo registry; all ten Project smart-button routes resolved to their correct Project-scoped models.
- Rollback evidence: database, filestore, configuration and pre-deployment active-module backups are retained under `/home/hongyi-jig-erp/releases/backups/20260829_095013` and `/home/hongyi-jig-erp/releases/rollback/2ffd5fd_predeploy_20260829_1048`.
- Production boundary: `odoo-production.service` remained active and was not stopped, upgraded or reconfigured.
- Pending release gate: a human must complete visual role/programme UAT on staging before any production decision.
