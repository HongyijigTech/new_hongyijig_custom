# Programme Template Migration Map

Status: production read-only evidence captured on 2026-08-27. No production task records were changed.

The final live ORM reconciliation supersedes an earlier Claude transcript whose Project 1 and
Project 2 per-stage subtotals were inaccurate. The live records had no task writes during this
work session; totals remain 141 and 22 respectively.

## Source programmes

| Legacy project | Programme | Tasks | Active | Archived | Activity-master linked | Native dependencies |
|---:|---|---:|---:|---:|---:|---:|
| 1 | LaunchGuard Complete | 141 | 141 | 0 | 0 | 0 |
| 2 | LaunchGuard Design | 22 | 22 | 0 | 0 | 0 |
| 3 | LaunchGuard Development | 127 | 127 | 0 | 0 | 0 |
| 4 | ToolLock Control | 106 | 106 | 0 | 0 | 0 |
| 5 | ToolLock Lite | 12 | 12 | 0 | 0 | 0 |

All 408 tasks are manual legacy template tasks. None is currently linked to a governed activity master, designation, SOP/Form master, or dependency rule.

## Exact stage distribution

### Project 1 - LaunchGuard Complete

| Legacy stage | Count | Canonical stage |
|---|---:|---|
| IG-01 - Project Planning Gate | 11 | PA-00 (legacy alias IG-01) |
| B1 / TG-01 - Design & Supplier Selection | 20 | TG-01 |
| B2 / TG-02 - Pre-Tooling Governance | 14 | TG-02 |
| B3 / TG-03 - Tool Manufacturing | 11 | TG-03 |
| B4 / TG-04 - T0 Review + T1 Execution | 13 | TG-04 |
| B4 / TG-05 - T1 Review + T2 Execution | 12 | TG-05 |
| B4 / TG-06 - Final Trial / Mould Buyoff | 13 | TG-06 |
| B5 / TG-07 - Dispatch Clearance | 14 | TG-07 |
| B6 / TG-08 - Shipment / India Delivery | 12 | TG-08 |
| B7 / TG-09 - Installation & Sign-Off | 10 | TG-09 |
| B8 / TG-10 - Project Closure (Full) | 11 | TG-10 |

### Project 2 - LaunchGuard Design

| Legacy stage | Count | Canonical stage |
|---|---:|---|
| IG-01 - Project Planning Gate | 12 | PA-00 (legacy alias IG-01) |
| B1 - Design Only / Design Sign-Off | 10 | LGD-SIGNOFF terminal milestone (not standard TG-01) |

### Project 3 - LaunchGuard Development

| Legacy stage | Count | Canonical stage |
|---|---:|---|
| IG-01 - Project Planning Gate | 11 | PA-00 (legacy alias IG-01) |
| Pre-B2 - Toolmaker Selection | 7 | PRE-B2 |
| B2 / TG-02 | 13 | TG-02 |
| B3 / TG-03 | 11 | TG-03 |
| B4 / TG-04 | 13 | TG-04 |
| B4 / TG-05 | 12 | TG-05 |
| B4 / TG-06 | 13 | TG-06 |
| B5 / TG-07 | 14 | TG-07 |
| B6 / TG-08 | 12 | TG-08 |
| B7 / TG-09 | 10 | TG-09 |
| B8 / TG-10 | 11 | TG-10 |

### Project 4 - ToolLock Control

| Legacy stage | Count | Canonical stage |
|---|---:|---|
| IG-01 - Project Planning Gate | 11 | PA-00 (legacy alias IG-01) |
| Pre-B2 - Toolmaker Selection | 7 | PRE-B2 |
| B2 / TG-02 | 13 | TG-02 |
| B3 / TG-03 | 11 | TG-03 |
| B4 / TG-04 | 13 | TG-04 |
| B4 / TG-05 | 12 | TG-05 |
| B4 / TG-06 | 13 | TG-06 |
| B5 / TG-07 - FOB programme end | 13 | TG-07 |
| B8 / TG-10-LITE | 13 | TG-10-LITE |

ToolLock Control intentionally excludes TG-08 and TG-09.

### Project 5 - ToolLock Lite

| Legacy stage | Count | Canonical stage |
|---|---:|---|
| Session 1 | 2 | TLL-S01 |
| Session 2 | 2 | TLL-S02 |
| Session 3 | 2 | TLL-S03 |
| Session 4 | 2 | TLL-S04 |
| Session 5 | 2 | TLL-S05 |
| Session 6 | 2 | TLL-S06 |

ToolLock Lite is an advisory service, not a gate-governed B-Series execution programme. Its 12
legacy task records are retained as immutable source references inside six advisory-session
template records (two references per session). It generates no programme gates, project tasks,
gate dependencies, or gate checklists. Each delivered session uses one approved blank controlled
framework and requires designation-based acceptance. Tooling execution monitoring remains outside
the ToolLock Lite scope.

## Canonical ownership decision

Module-owned `hjig.*` models are the system of record. Studio `x_*` models remain read-only migration sources until their content and relationships have been reconciled and validated.

The canonical stage master is the verified union of the five programme routes:

- PA-00 with legacy alias IG-01
- TG-01 through TG-09
- PRE-B2
- TG-10 full closure
- TG-10-LITE controlled closure
- TLL-S01 through TLL-S06 advisory sessions

TG-09 is an execution gate. Full closure is TG-10. Lite closure is TG-10-LITE.

## Migration gates

No programme version may be approved until:

1. every governed-programme source task is mapped to a canonical stage and stable activity code;
   ToolLock Lite instead reconciles all 12 source references into exactly six session records;
2. owner and approver designations are assigned;
3. mandatory SOP/Form rules are selected for that programme version;
4. dependencies and timing offsets are explicitly defined rather than inferred from task order;
5. the migrated task count and per-stage counts reconcile exactly to this register;
6. the generated definition hash is retained in the immutable programme-run snapshot.

The five template masters are created in draft state only. No legacy project is deleted or rewritten by this migration.
