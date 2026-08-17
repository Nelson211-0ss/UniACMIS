# UniACMIS — Phase 1 Task Breakdown

Scope for review before feature code is written. Phase 1 is **Foundation**: nothing here is a user-facing
academic feature. Its purpose is that Phases 2–6 can each be built without renegotiating identity,
permissions, auditing, configuration or offline sync.

Requirement IDs refer to the SRS; coverage is tracked in [TRACEABILITY.md](TRACEABILITY.md). Work packages
are listed in dependency order.

**Definition of done for Phase 1 as a whole**

- `make up && make migrate && make seed && make test && make lint` all succeed from a clean clone
- A registrar can run the full Phase 1 registry workflow through the Django admin unaided
- Every grade-relevant and money-relevant write path already produces a verifiable audit entry
- An offline-queued write survives a disconnect, syncs once on reconnect, and cannot be double-applied
- Every endpoint's authorisation is asserted by the permission-matrix test

---

## WP1 — Project scaffolding

| # | Task | Requirements | Acceptance criteria |
|---|---|---|---|
| 1.1 | Repo layout: `backend/`, `frontend/`, `docs/`, `Makefile`, `.gitignore`, `.editorconfig` | — | Structure matches ARCHITECTURE.md §3 |
| 1.2 | Django 5.2 project with split settings (`base`/`dev`/`prod`), `django-environ` | `NFR-MAINT-02` | `dev` runs with no secrets in source; `prod` refuses to boot with `DEBUG=True` or a default `SECRET_KEY` |
| 1.3 | `docker-compose.yml`: `db` (postgres:16), `redis`, `backend`, `worker`, `beat`, `frontend`; `minio` + `mailpit` behind profiles | `NFR-MAINT-02` | `make up` gives healthy containers; Postgres data persists across `down`/`up` |
| 1.4 | `.env.example` documenting every variable | — | A new machine boots from `cp .env.example .env` and nothing else |
| 1.5 | Celery app + Redis broker, one smoke task, beat schedule stub | — | `make up` then a queued task executes in the worker log |
| 1.6 | Tooling: `ruff`, `black`, `pytest`+`pytest-django`, `factory_boy`, `coverage`, `import-linter` in `pyproject.toml` | — | `make lint` and `make test` run green on the empty project |
| 1.7 | GitHub Actions CI: lint, import contracts, migration check, tests on a Postgres service | — | CI green on first push; `makemigrations --check --dry-run` fails the build on model drift |
| 1.8 | `Makefile`: `up down migrate seed test lint fmt shell logs` | — | Documented in the README and each target works |

---

## WP2 — `core`: shared foundation

| # | Task | Requirements | Acceptance criteria |
|---|---|---|---|
| 2.1 | `TimeStampedModel`, `SoftDeleteModel` + manager excluding deleted rows by default | — | Unit tests cover that default managers hide soft-deleted rows and `all_objects` reveals them |
| 2.2 | `MoneyField` + `CurrencyMixin` (amount, currency, fx_rate, fx_rate_date) | SRS §2.5 | Cannot persist an amount without a currency; a cross-currency value without an FX rate raises |
| 2.3 | Service registry for cross-module providers (`registry.register` / `get_all`) | `NFR-MAINT-01` | Registration at `AppConfig.ready()`; resolution works with the implementing app absent |
| 2.4 | `NotificationProvider` + `PaymentProvider` protocols with `Console`/`Mock` implementations, selected by settings | `FR-COM-01/02`, `FR-FIN-03` | Swapping providers is a settings change; mocks record calls for assertions |
| 2.5 | Consistent API error envelope via a custom DRF exception handler; `request_id` middleware + `X-Request-ID` | §10 conventions | Every 4xx/5xx returns the documented shape with a `request_id` that also appears on audit rows |
| 2.6 | `drf-spectacular` wired; `/api/v1/schema/`, Swagger UI | — | Schema generates with no warnings; every endpoint declares auth and response types |
| 2.7 | Bounded page-number pagination (cursor for append-only tables) + `django-filter` defaults | `NFR-PERF-01` | No list endpoint can return an unbounded result set |
| 2.8 | `IdSequence` model + `allocate(scope)` under `select_for_update()` | `FR-REG-01` | Concurrency test: N parallel transactions on one scope yield N distinct gapless values |
| 2.9 | i18n enabled, strings through `gettext` | `NFR-USE-01` | `makemessages` extracts; no user-facing literal is hard-coded |

---

## WP3 — `accounts`: authentication and RBAC

Built before any module feature, because almost every endpoint needs a role check and retrofitting
authorisation is how gaps happen.

| # | Task | Requirements | Acceptance criteria |
|---|---|---|---|
| 3.1 | Custom `User` (email login, `phone`, `mfa_enabled`, `must_change_password`) + manager | `NFR-SEC-04` | `createsuperuser` works; email is case-insensitively unique |
| 3.2 | `Role` (⇄ `auth.Group`) and `UserRole` through-model with grant/revoke history | `NFR-SEC-01` | Grants and revocations appear in the audit log with the granting actor |
| 3.3 | Declarative permission registry for all SRS roles (13 — `senate` split from `management`) | `NFR-SEC-01` | One file states the whole authorisation policy; reviewable in a single diff |
| 3.4 | Idempotent `seed_roles` management command | `NFR-MAINT-03` | Re-running changes nothing; adding a permission to the registry and re-running applies just that |
| 3.5 | `HasModulePermission` DRF class reading `required_permission` from the view | `NFR-SEC-01` | A view without a declared permission fails a guard test rather than defaulting to open |
| 3.6 | `ScopedQuerysetMixin` for row-level narrowing per role | `NFR-SEC-01` | A lecturer's student list contains only their own course's students |
| 3.7 | JWT auth: login, refresh with rotation + blacklist, logout, `/me` | — | A revoked refresh token is rejected; access tokens are short-lived |
| 3.8 | Password policy, throttled login, lockout after repeated failures | `NFR-SEC-04` | Brute-force test: repeated failures lock the account and are audited |
| 3.9 | Separation of duties assertion | `NFR-SEC-01` | Test proves no non-`ict_admin` role holds both grade-write and money-write permissions |

---

## WP4 — `audit`: tamper-evident trail

| # | Task | Requirements | Acceptance criteria |
|---|---|---|---|
| 4.1 | `AuditLog` model with field-level old/new, actor snapshotting, `request_id`, `reason` | `FR-RPT-04`, SRS §6 | Row survives deletion of the actor with the name and role still readable |
| 4.2 | Hash chain (`prev_hash`, `row_hash`) written server-side | `FR-RPT-04` | Chain verifies; editing a historical row via raw SQL is detected |
| 4.3 | `verify_audit_chain` management command | `FR-RPT-04` | Reports the first broken link with its row id; exits non-zero on failure |
| 4.4 | `AuditedModel` mixin diffing declared `audit_fields` | `FR-RPT-04` | Updating a tracked field produces one row per changed field; untracked fields produce none |
| 4.5 | `AuditActorMiddleware` (thread-local actor) + `system` fallback for Celery and commands | `NFR-SEC-03` | Admin edits, API writes and management commands are all attributed |
| 4.6 | Append-only enforcement + documented production DB grants | `FR-RPT-04` | No code path updates/deletes; the documented role lacks `UPDATE`/`DELETE` on the table |
| 4.7 | Transactional coupling for grade/money writes | `FR-RPT-04` | Test: a forced audit-write failure rolls back the accompanying sensitive change |
| 4.8 | `view_sensitive` access logging hook + retention documentation | `NFR-SEC-03` | Reading a sensitive record via the designated mixin is logged; 5-year retention documented |
| 4.9 | Read-only admin for the audit log with filters | `FR-RPT-04` | Registrar/ICT can search by entity, actor, date; no add/change/delete buttons |

---

## WP5 — `academics`: institutional configuration

| # | Task | Requirements | Acceptance criteria |
|---|---|---|---|
| 5.1 | `Institution` incl. `student_id_template`, currencies, attendance threshold, MoHEST code | `NFR-MAINT-03` | Editable in admin; no code reads a hard-coded institutional constant |
| 5.2 | `AcademicYear` with a single-`is_current` guarantee | `FR-ENR-01` | Partial unique index + `clean()`; making a second year current is rejected |
| 5.3 | `Semester` with teaching, exam, registration and add/drop windows | `FR-ENR-01` | Date ranges validated as ordered and non-overlapping within a year |
| 5.4 | `GradingScale` / `GradeBand` with full-cover, no-overlap validation | `FR-EXM-04`, `NFR-MAINT-03` | Gaps, overlaps and out-of-range grade points are all rejected with clear messages |
| 5.5 | Immutability of a scale once referenced by published results | `FR-EXM-04` | Test asserts the guard (hook present now; results arrive Phase 3) |
| 5.6 | Pure `grade_for()`, `gpa()`, `cgpa()` in `services/grading.py` | `FR-EXM-04` | Unit tests incl. boundary percentages, credit weighting, rounding, empty input |
| 5.7 | Calendar query service (`is_registration_open()`, `current_semester()`) | `FR-ENR-01` | Modules ask the calendar; no module compares dates itself |

---

## WP6 — `curriculum`: academic structure

| # | Task | Requirements | Acceptance criteria |
|---|---|---|---|
| 6.1 | `Faculty`, `Department` with codes, dean/head links | `FR-CUR-01` | Codes unique; soft delete preserves history |
| 6.2 | `Programme` incl. credit limits and `entry_requirements` JSON | `FR-CUR-01`, `FR-ADM-03` | Admin-manageable; credit ceilings available to Phase 2 validation |
| 6.3 | `Course` owned by a department, with credit hours and level | `FR-CUR-02` | A service course is defined once and reused by several curricula |
| 6.4 | `CurriculumVersion` + `CurriculumCourse` (core/elective, year, semester) | `FR-CUR-03` | Retiring a version leaves existing students bound to their original one |
| 6.5 | `Prerequisite` with self-reference and cycle rejection | `FR-CUR-02` | Cycle test: A→B→C→A is rejected on save |
| 6.6 | Programme credit-total consistency report | `FR-CUR-02` | Flags a curriculum version whose core credits cannot reach the graduation requirement |

---

## WP7 — `registry`: students and staff

| # | Task | Requirements | Acceptance criteria |
|---|---|---|---|
| 7.1 | `Student` with full bio-data incl. gender, disability, state of origin as constrained choices | `FR-REG-02`, `FR-RPT-03` | Statutory disaggregation is aggregatable without cleaning free text |
| 7.2 | Template-driven student ID generation over `IdSequence` | `FR-REG-01` | Concurrency test yields no duplicates; withdrawn IDs are never reissued |
| 7.3 | `StudentStatusHistory` with mandatory reason, written on every transition | `FR-REG-04` | Status cannot change without a reason; history is append-only |
| 7.4 | `NextOfKin` (one primary enforced), `Sponsor` | `FR-REG-02`, `FR-FIN-04` | Second primary next-of-kin rejected |
| 7.5 | `StudentDocument` with size cap and content hash | `FR-REG-03` | Oversized upload rejected; substituting a verified file is detectable |
| 7.6 | `StaffProfile` with category, rank, appointment type | `FR-HR-01` | Referenced by `Department.head` / `Faculty.dean` |
| 7.7 | DRF endpoints for students, staff and curriculum reads, all permission-guarded | `NFR-SEC-01` | Present in the permission matrix; a lecturer cannot list the full registry |
| 7.8 | `RegistrationHoldService` + `HoldProvider` registry + fake finance provider | `FR-ENR-03` | Integration test: an unpaid-fee hold blocks a registration attempt with the finance module absent |

---

## WP8 — Offline sync spine

| # | Task | Requirements | Acceptance criteria |
|---|---|---|---|
| 8.1 | `SyncOperation` ledger with unique `client_op_id` | `NFR-AVAIL-01` | Replaying a batch returns the stored result and applies nothing twice |
| 8.2 | `POST /api/v1/sync/batch` with independent per-operation results | `NFR-AVAIL-01` | One rejected operation does not block the rest of the batch |
| 8.3 | `SyncHandler` protocol + registry (entity, permission, conflict policy) | `NFR-AVAIL-01` | Phase 3 can register attendance without touching the engine |
| 8.4 | `LAST_WRITE_WINS` policy writing the overwritten value to the audit log | `NFR-AVAIL-01` | A lost update is reconstructable from the audit trail |
| 8.5 | `FLAG_FOR_REVIEW` policy + `SyncConflict` + `409` | `NFR-AVAIL-01`, `FR-RPT-04` | A divergent write is never applied silently; the conflict row holds both versions |
| 8.6 | Conflict resolution endpoint + admin (mandatory resolution reason) | `NFR-AVAIL-01` | Resolving requires a reason and is audited |
| 8.7 | Handler for `registry.student` creation | `FR-REG-01`, `NFR-AVAIL-01` | Clerk creates students offline; IDs still unique after sync |
| 8.8 | Sync test suite: replay, duplicate, conflict, clock skew, partial batch failure | `NFR-AVAIL-01` | Explicit test that a device with a badly wrong clock cannot overwrite newer server data under `FLAG_FOR_REVIEW` |

---

## WP9 — Frontend PWA shell

Thin by decision: the Django admin remains the registrar's working UI through Phase 1. What matters here is
proving the offline mechanism the later modules depend on.

| # | Task | Requirements | Acceptance criteria |
|---|---|---|---|
| 9.1 | Next.js 15 App Router project running on `node:20` in Compose | — | `make up` serves it on `:3000` |
| 9.2 | "Academic Nexus" design tokens as CSS custom properties, mobile-first | `NFR-USE-02` | Usable at 5-inch width; matches the supplied palette |
| 9.3 | JWT login, refresh-on-401, secure token storage, logout | — | Session survives a reload; expiry redirects cleanly |
| 9.4 | Role-aware navigation shell from `/me` | `NFR-SEC-01` | Nav shows only what the role may reach; hiding is cosmetic — the API is the boundary |
| 9.5 | Service worker: app-shell network-first with offline fallback, stale-while-revalidate for assets, installable manifest | `NFR-PERF-01` | Lighthouse PWA install criteria met; shell loads with the network off |
| 9.6 | IndexedDB outbox (`idb`): enqueue, flush oldest-first, exponential backoff | `NFR-AVAIL-01` | Queued items survive a browser restart |
| 9.7 | Offline UX: connection indicator, pending count, per-item state, conflict surface | `NFR-AVAIL-01` | A queued write is shown as pending, never as saved |
| 9.8 | End-to-end offline student-creation form | `NFR-AVAIL-01` | The manual drill in the README passes: offline submit → reconnect → single record |

---

## WP10 — Admin, seeding, documentation

| # | Task | Requirements | Acceptance criteria |
|---|---|---|---|
| 10.1 | Django admin configured for registrar/ICT use: list displays, search, filters, inlines, sensible ordering | — | A registrar can complete the Phase 1 workflow without a developer |
| 10.2 | Admin branding + per-model permissions honouring roles | `NFR-SEC-01` | Finance staff cannot reach curriculum models |
| 10.3 | `seed_roles` (production-safe) and `seed_demo` (dev only, refuses to run with `DEBUG=False`) | `NFR-MAINT-03` | Demo data: institution, 2 faculties, 4 programmes, ~20 courses, 2026/2027 with 2 semesters, 4.00 scale, one user per role, ~30 students |
| 10.4 | README: setup, env vars, migrations, seeding, tests, offline drill, backup/restore | `NFR-DATA-01` | A new developer is productive from the README alone |
| 10.5 | `CLAUDE.md` / contributing notes: conventions, boundary rules, how to add a module | `NFR-MAINT-01` | New module work follows the pattern without re-reading every file |

---

## WP11 — Test suite

| # | Task | Requirements | Acceptance criteria |
|---|---|---|---|
| 11.1 | Unit: grading validation, `gpa()`/`cgpa()`, ID generation, hash chain, money field | `FR-EXM-04`, `FR-REG-01` | Boundary cases covered, not just happy paths |
| 11.2 | Integration: hold blocking registration via a fake provider | `FR-ENR-03` | Passes with `finance` not installed |
| 11.3 | Permission matrix across every role × endpoint | `NFR-SEC-01` | Parametrised; a new unguarded endpoint fails CI |
| 11.4 | Sync suite (see 8.8) | `NFR-AVAIL-01` | |
| 11.5 | Audit coverage test: every `AuditedModel` write produces entries | `FR-RPT-04` | Reflection-driven, so a new audited model is covered automatically |
| 11.6 | Import-linter contracts | `NFR-MAINT-01` | A deliberate cross-app model import fails the build |
| 11.7 | Coverage reporting with a floor on `core`, `accounts`, `audit`, `academics` | — | Reported in CI |

---

## Out of scope for Phase 1

Admissions intake and review · course registration · timetabling · attendance UI · marks, moderation,
Senate approval · fee structures, invoicing, payments, reconciliation · leave, appraisal, payroll export ·
library · hostel · transcripts, certificates, QR verification · SMS and mobile-money integrations · MoHEST
exports · dashboards · `Campus` and campus↔central replication (deferral **D-1**) · load and penetration
testing (Phase 7).

## Review gate

Phase 1 ends with a demonstration of: the registry workflow in the admin, the audit trail with a verified
hash chain, the permission matrix output, and the offline drill. Phase 2 (Admissions & Enrollment) does not
begin until that is accepted.
