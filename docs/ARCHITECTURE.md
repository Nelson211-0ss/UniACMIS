# UniACMIS — Architecture

University Academic Management Information System for universities operating in South Sudan.

This document defines the architectural style, module boundaries, and the cross-cutting contracts
(audit, RBAC, offline sync, providers) that every module must build against. It is the reference for
"where does this code go?" and "how may this module talk to that one?".

Requirement IDs (`FR-*`, `NFR-*`) refer to `ACMIS_System_Requirements_Specification.docx`. See
[TRACEABILITY.md](TRACEABILITY.md) for full coverage tracking.

---

## 1. Operating constraints that drive the design

These are not preferences; they are the reason several choices below look more defensive than a typical
web application would need.

| Constraint | Architectural response |
|---|---|
| Intermittent internet (`NFR-AVAIL-01`) | Offline-first modules with a client-side outbox and an idempotent sync endpoint |
| Intermittent power (`NFR-AVAIL-02`) | PostgreSQL WAL durability, short transactions, no multi-request server-side state, frequent client autosave |
| 2G/3G bandwidth (`NFR-PERF-01`) | PWA app-shell precache, paginated APIs, no heavy client bundles, compressed uploads |
| On-premise per campus (`NFR-MAINT-02`) | Docker Compose deployment, no managed-cloud dependency, S3-compatible storage via MinIO |
| Feature phones (`NFR-USE-03`) | `NotificationProvider` abstraction with SMS as a first-class channel, not an add-on |
| SSP primary / USD secondary (§2.5) | Money is always `(amount, currency)` plus a recorded FX rate — never a bare decimal |
| Grade and money fraud risk (checklist §1) | Append-only, hash-chained audit trail; RBAC separating academic, finance and admin duties |
| 500 concurrent users/campus (`NFR-PERF-02`) | Stateless app tier behind gunicorn, Celery for anything slow, indexed query paths |

### Money is never a bare decimal

Every monetary field in this system is stored as a `DECIMAL` **plus** an explicit ISO currency code, and
any cross-currency figure additionally records the FX rate and the date it was captured. SSP inflation
makes a historical amount meaningless without the rate that applied when it was recorded. This rule is
stated here, in Phase 1, because retrofitting currency onto a finance module is a data-migration problem
with no clean answer. Enforced by the `MoneyField`/`CurrencyMixin` pair in `apps/core`.

---

## 2. Architectural style: modular monolith

One Django project, one database, many independently-reasoned apps. Deployed as a single unit — which is
what an on-premise campus server with an ICT department of two people can actually operate — but
internally partitioned so that a module can later be extracted into its own service without unpicking
every query in the codebase.

The partition is only real if something enforces it. See §4.

```
┌──────────────────────────────────────────────────────────────────────┐
│  Next.js PWA  ·  service worker + IndexedDB outbox  ·  JWT           │
└───────────────────────────────┬──────────────────────────────────────┘
                                │  HTTPS  /api/v1/
┌───────────────────────────────▼──────────────────────────────────────┐
│  Django + DRF                                                        │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ Module apps: admissions · registry · curriculum · enrollment   │  │
│  │ timetabling · attendance · examinations · finance · hr         │  │
│  │ library · hostel · documents · communications · alumni          │  │
│  │ reporting                                                      │  │
│  └────────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ Cross-cutting: core (base models, sync engine, providers)      │  │
│  │ accounts (RBAC) · audit (hash-chained log) · academics (config) │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────┬───────────────────────────┬─────────────────────┬─────────────┘
       │                           │                     │
┌──────▼──────┐            ┌───────▼───────┐     ┌───────▼────────┐
│ PostgreSQL  │            │ Redis + Celery│     │ MinIO / local  │
│ 16          │            │ (SMS, reports,│     │ FS (documents) │
│             │            │  sync recon.) │     │                │
└─────────────┘            └───────────────┘     └────────────────┘
```

---

## 3. App breakdown

`Phase` is the build phase from the implementation plan. Only Phase 1 apps exist as real Django apps
today; the rest are created when their phase begins. Empty placeholder packages are dead weight and
obscure which boundaries are actually enforced.

| App | Responsibility | Phase | Status |
|---|---|---|---|
| `core` | Abstract base models, money types, shared reference choices, service registry, sync engine, provider interfaces, permission class, error shape | 1 | **built** |
| `accounts` | `User`, `Role`, RBAC registry, DRF permission classes, JWT auth | 1 | **built** |
| `audit` | Hash-chained append-only `AuditLog`, `AuditedModel` mixin, actor middleware | 1 | **built** |
| `academics` | `Institution`, academic calendar, `GradingScale`/`GradeBand`, GPA computation | 1 | **built** |
| `curriculum` | Faculty → Department → Programme → Course, curriculum versioning, prerequisites | 1 | **built** |
| `registry` | `Student`, `StaffProfile`, status history, next-of-kin, sponsor, document vault | 1 | **built** |
| `admissions` | Application intake (online + staff entry), review workflow, merit lists, offers | 2 | planned |
| `enrollment` | Course registration, prerequisite/credit validation, holds, class lists | 2 | planned |
| `timetabling` | Class and exam timetables, clash detection, room/invigilator allocation | 3 | planned |
| `attendance` | Session registers, offline capture, threshold alerts | 3 | planned |
| `examinations` | CA and final marks, moderation, GPA/CGPA, Senate approval gate | 3 | planned |
| `finance` | Fee structures, invoicing, payments, reconciliation, scholarships, refunds | 4 | planned |
| `hr` | Staff contracts, qualifications, leave, appraisal, payroll export | 5 | planned |
| `library` | Catalogue, circulation with offline sync, fines | 5 | planned |
| `hostel` | Room inventory, allocation rules, occupancy | 5 | planned |
| `documents` | Transcripts, certificates, QR/serial verification, graduation clearance | 6 | planned |
| `communications` | SMS/email/portal notices, bulk messaging, templates | 6 | planned |
| `alumni` | Post-graduation contacts, tracer studies, events | 6 | planned |
| `reporting` | Dashboards, MoHEST statutory exports, disaggregated reporting | 6 | planned |

`academics` is an addition to the module list in the original brief. `NFR-MAINT-03` requires the academic
calendar and grading scale to be data-driven configuration, and that configuration is read by
`enrollment`, `examinations`, `finance` and `reporting` alike — it belongs to no single one of them. Giving
it an explicit owner keeps it from silting up in `core`, which would then be imported by everything for
unrelated reasons.

---

## 4. Module boundary rules

**Rule 1 — no cross-app model imports.** A module may import from `core`, `accounts`, `audit` and
`academics` (the cross-cutting layer). It may not import another *module's* models, managers or
serializers.

**Rule 2 — modules talk through `services.py`.** Each module exposes a public service API as plain
functions with typed, primitive-ish signatures. That function is the module's contract; its models are
private implementation detail.

**Rule 3 — inbound dependencies are inverted where the caller is lower down the stack.** When
`enrollment` needs to know whether a student owes fees, it does not call `finance`. It asks a registry of
providers that `finance` registers into. This is what keeps Phase 2 buildable before Phase 4 exists, and
what allows `finance` to be extracted to a service later.

```python
# apps/enrollment/services.py — the caller knows only the interface
from apps.core.services import registry

def check_registration_holds(student_id: int) -> list[Hold]:
    """Collect holds from every registered provider (finance, discipline, documents)."""
    return [h for p in registry.get_all(HoldProvider) for h in p.holds_for(student_id)]
```

```python
# apps/finance/providers.py — the implementer registers itself at app-ready time
@registry.register(HoldProvider)
class FeeBalanceHoldProvider:
    def holds_for(self, student_id: int) -> list[Hold]: ...
```

**Enforcement.** These rules are checked by `import-linter` contracts in `pyproject.toml`, run in CI. A
direct cross-app model import fails the build. "Loosely coupled" that nothing verifies degrades within a
sprint or two, so this is wired up in Phase 1 while there are only six apps to keep honest.

---

## 5. Cross-cutting contract: audit trail

`FR-RPT-04` requires a **tamper-evident** trail for all grade and financial data; `NFR-SEC-03` requires
5-year retention of access and modification records.

- **Append-only.** No update or delete path exists in code; the DB role used by the application is not
  granted `UPDATE`/`DELETE` on `audit_auditlog` in production.
- **Field-level.** One row per changed field, carrying `old_value` and `new_value` as text.
- **Actor snapshotting.** `actor` is a nullable FK, but `actor_name` and `actor_role` are copied in as
  text at write time, so the entry stays readable after a user is renamed or deleted.
- **Hash chain.** Each row stores `prev_hash` and `row_hash = sha256(prev_hash + canonical_payload)`. A
  `verify_audit_chain` management command re-walks the chain. Deleting or editing a historical row breaks
  it detectably — which is the difference between tamper-*evident* and merely tamper-*logged*.
- **How writes are captured.** Models inherit `AuditedModel` and declare `audit_fields`; a `post_init` +
  `pre_save` diff produces the entries. Non-ORM writes call `audit.services.record_change()` explicitly.
  The actor comes from a thread-local set by `AuditActorMiddleware`, falling back to `system` for Celery
  tasks and management commands.

Audit writes are best-effort in the sense that a logging failure is reported loudly but must not corrupt
the transaction it describes — *except* for grade and financial writes, where the audit row is written in
the same transaction and a failure rolls the change back. Losing the record of a mark change is worse
than failing the mark change.

---

## 6. Cross-cutting contract: RBAC

`NFR-SEC-01` requires least-privilege RBAC with strict separation between academic, finance and admin
duties. Roles are drawn from SRS §2.2.

`applicant` · `student` · `lecturer` · `hod` · `registrar` · `finance` · `examinations` · `senate` ·
`hr` · `library` · `hostel` · `ict_admin` · `management`

Thirteen, not the twelve the SRS lists: **`senate` is split out from `management`**. `FR-EXM-05`
requires Senate approval before results are published, and if the examinations office held both
`change_mark` and `approve_result` that gate would be decorative. Splitting the role is what makes the
approval an independent authority. Asserted by
`tests/test_permission_matrix.py::test_result_approval_is_separate_from_result_processing`.

- **Declarative registry.** `apps/accounts/roles.py` maps each role to a list of Django
  permission codenames. `manage.py seed_roles` applies it idempotently — safe to re-run on every deploy,
  so a policy change is a data operation rather than a code change.
- **One enforcement point.** DRF views declare `required_permission = "registry.view_student"`, and
  `HasModulePermission` checks it. Role-name string comparisons scattered through views are how
  authorisation logic rots; there are none.
- **Row-level scoping.** `ScopedQuerysetMixin` narrows the queryset per role — a lecturer sees the
  students on their own courses, not the whole registry. Object permissions are checked on detail routes,
  not only on lists.
- **Separation of duties.** No single non-`ict_admin` role holds both grade-write and fee-write
  permissions. `ict_admin` can administer accounts but is not granted grade or money write permissions;
  privilege escalation by an ICT officer is therefore visible in the audit trail as a role change.
- **MFA.** `NFR-SEC-04` requires MFA availability for finance and registrar roles. The `User.mfa_enabled`
  flag and enforcement hook exist from Phase 1; the TOTP enrolment flow lands with the finance module.
- **Coverage test.** A parametrised permission-matrix test asserts the outcome for every role × endpoint
  pair. A new endpoint that forgets its permission class fails CI instead of shipping open.

---

## 7. Cross-cutting contract: offline-first sync

Applies to attendance (`FR-ATT-01`), grade entry (`FR-EXM-02`) and library circulation (`FR-LIB-03`), and
to registry data entry during outages. The contract is defined and proven in Phase 1 so that the modules
which depend on it are not each inventing their own.

### Client side

1. A user action produces an **operation** with a client-generated UUID (`client_op_id`), the target
   entity, a payload, and the client's timestamp.
2. Online, it posts immediately. Offline, it goes into an **IndexedDB outbox** and the UI shows it as
   pending — never as saved.
3. On reconnect (`online` event, or periodic retry) the outbox flushes oldest-first, with exponential
   backoff. Operations are retried until acknowledged; the client never drops one silently.

### Server side

`POST /api/v1/sync/batch`

```json
{ "operations": [ {
      "client_op_id": "550e8400-e29b-41d4-a716-446655440000",
      "entity": "registry.student",
      "action": "create",
      "payload": { "...": "..." },
      "client_timestamp": "2026-08-17T09:14:03Z"
} ] }
```

- **Idempotent by construction.** `client_op_id` is unique. A replayed operation is not re-applied; the
  stored result of the first application is returned. This is what makes "retry the whole batch after the
  connection dropped mid-flush" safe, which is the normal case here, not the edge case.
- **Per-operation results.** The response reports each operation independently (`applied`, `duplicate`,
  `conflict`, `rejected`) so one bad row cannot block a batch of ninety good ones.
- **Handlers are registered per entity**, declaring their own validation, permission and conflict policy:

```python
class SyncHandler(Protocol):
    entity: str
    conflict_policy: ConflictPolicy          # LAST_WRITE_WINS | FLAG_FOR_REVIEW
    required_permission: str
    def apply(self, op: SyncOperation, actor: User) -> SyncResult: ...
```

- **Conflict policy.**
  - `LAST_WRITE_WINS` — the later `client_timestamp` wins; the overwritten value is written to the audit
    trail, so a lost update is always reconstructable. Default for attendance and circulation.
  - `FLAG_FOR_REVIEW` — a divergent concurrent write is **not** applied. It creates a `SyncConflict` row
    holding both versions for a human to resolve. Mandatory for anything touching
    marks or money: silently overwriting a grade because a laptop's clock was ahead is a fraud vector,
    not a merge strategy.
- **Clock skew is assumed.** Client timestamps come from devices that may be badly wrong, so they are
  recorded and used for ordering *within* a client's own stream, while server receipt time is what
  audit entries and reports use.

### What Phase 1 delivers

The engine, one registered handler (`registry.student` creation for clerks working through an outage), the
IndexedDB outbox, and tests covering replay, duplicate suppression and conflict flagging. Phase 3's
attendance and grade entry then register handlers rather than building sync.

---

## 8. Provider abstractions

Business logic must never import a vendor SDK. Both interfaces below are defined in Phase 1 with a mock
implementation, so the modules that consume them can be built and tested before any commercial
integration exists — and so that swapping aggregator is a settings change.

```python
class NotificationProvider(Protocol):                      # FR-COM-01, FR-COM-02, NFR-USE-03
    def send_sms(self, to: str, body: str, ref: str) -> DeliveryReceipt: ...
    def send_email(self, to: str, subject: str, body: str, ref: str) -> DeliveryReceipt: ...

class PaymentProvider(Protocol):                           # FR-FIN-03
    def initiate(self, amount: Money, payer_ref: str, invoice_ref: str) -> PaymentIntent: ...
    def status(self, intent_ref: str) -> PaymentStatus: ...
    def verify_callback(self, request) -> PaymentEvent: ...  # signature verification included
```

Selected by settings (`NOTIFICATION_PROVIDER`, `PAYMENT_PROVIDER`). Phase 1 ships
`ConsoleNotificationProvider` and `MockPaymentProvider`; MTN MoMo / Zain Cash–M-Gurush and a local SMS
aggregator plug in at Phases 4 and 6. All provider calls run in Celery tasks with retry and a persisted
delivery/receipt log — an SMS that failed to send must be visible, not lost.

---

## 9. Configuration over hard-coding

`NFR-MAINT-03`: fee structures, grading scales, academic calendars and quota rules are data, editable by
authorized staff, not constants. Practically:

- Grading bands live in `academics.GradeBand`, validated to cover 0–100 with no gap or overlap. Nothing
  computes a letter grade from an `if` ladder.
- The academic calendar (`AcademicYear`, `Semester`, and later registration/exam windows) governs *when*
  operations are permitted (`FR-ENR-01`); modules ask the calendar rather than checking dates themselves.
- Student ID format is a template string (`{faculty}/{programme}/{year}/{seq:04d}`), per `FR-REG-01` and
  the checklist's faculty/year alignment requirement.
- Institution-level settings (name, MoHEST code, default currency, thresholds such as the 75% attendance
  bar) are rows, not deploy-time constants.

---

## 10. API conventions

- Versioned under `/api/v1/`. Breaking changes get `/api/v2/`, not a silent shape change.
- OpenAPI 3 auto-generated by `drf-spectacular`; Swagger UI at `/api/v1/schema/swagger-ui/`.
- **Consistent error envelope** from a single custom exception handler:

```json
{ "error": { "code": "validation_error",
             "message": "Registration blocked by an outstanding hold.",
             "details": { "holds": ["Unpaid fees: SSP 45,000"] },
             "request_id": "01JZ8QK3F7Y2A9BCDEF" } }
```

- `request_id` is generated per request, returned in the body and the `X-Request-ID` header, and stored on
  audit rows — so a user's screenshot is enough to find the exact server-side trail.
- Page-number pagination with a hard `max_page_size` for administrative lists (staff need a total
  count to page through a register); cursor pagination for append-only, high-volume tables such as
  the audit log, where `COUNT(*)` would dominate the response. `django-filter` for list filtering.
- JWT access (short-lived) + refresh, via `djangorestframework-simplejwt`. Rotating refresh tokens with
  blacklist, so a stolen token on a shared campus machine can be revoked.
- All timestamps are UTC in the API; presentation-layer localisation only (Africa/Juba).

---

## 11. Deployment topology

Primary deployment is **one instance per campus, on premise** (`NFR-MAINT-02`, §2.4), with the central
instance used for backup, DR and cross-campus reporting rather than as the system of record.

```
Campus server (Linux + UPS/solar)          Central instance (cloud or HQ)
┌──────────────────────────────┐           ┌──────────────────────────────┐
│ nginx → gunicorn (Django)    │           │ Reporting replica            │
│ Celery worker + beat         │  ──sync──▶│ Off-site backup store        │
│ PostgreSQL 16 (system of     │  when      │ Cross-campus dashboards      │
│ record) · Redis · MinIO      │  bandwidth │                              │
│ Nightly pg_dump → off-site   │  allows    │                              │
└──────────────────────────────┘           └──────────────────────────────┘
```

Backups (`NFR-DATA-01`): nightly `pg_dump` retained locally, replicated off-site opportunistically. The
restore procedure is documented and rehearsed — an untested backup is not a backup.

**Multi-campus is deferred by decision.** Phase 1 models a single campus. The checklist's multi-campus
objective and `FR-COM-03`'s per-campus audience remain open; adding a `Campus` FK later will touch most
tables and every scoped query, and that cost is accepted knowingly. Recorded in
[TRACEABILITY.md](TRACEABILITY.md). Postgres logical replication is the intended sync mechanism for
central reporting; the campus↔central protocol is specified when Phase 7 hardening begins.

---

## 12. Technology choices

| Layer | Choice | Version | Why |
|---|---|---|---|
| Backend | Django + DRF | 5.2 LTS / 3.16 | LTS support window; admin panel is a usable registrar UI on day one |
| Database | PostgreSQL | 16 | Matches local `psql 16.14`; strong durability under ungraceful shutdown |
| Frontend | Next.js (App Router) PWA | 15 | Works on the installed Node 18.19; runs on `node:20` in Compose |
| Offline storage | IndexedDB via `idb` | — | Only durable browser store adequate for a write outbox |
| Service worker | hand-written (`frontend/public/sw.js`) | — | The caching rules here are specific (never serve a stale student record, never intercept a write) and the outbox logic is custom anyway; a plugin would add a dependency and a build step without removing any of that |
| Async | Celery + Redis | 5.4 / 7 | SMS, reports, sync reconciliation |
| Auth | SimpleJWT over Django auth | — | Django's hasher and session security, JWT for the PWA |
| Files | local FS or MinIO | — | S3 API without a cloud dependency |
| Docs | drf-spectacular | — | Schema generated from code, so it cannot drift |
| Quality | pytest · ruff · black · import-linter | — | Tests and boundary contracts from Phase 1 |

---

## 13. Testing strategy

Per SRS §7.2, and from Phase 1 onward rather than deferred:

- **Unit** — pure business logic: GPA/CGPA computation, grading-scale validation, fee balance (Phase 4),
  hold rules, student-ID generation.
- **Integration** — cross-module flows through service interfaces: unpaid fees blocking registration,
  attendance threshold blocking exam registration, Senate approval gating result publication.
- **Offline/sync** — simulated disconnection mid-write, replayed batches, duplicate suppression, conflict
  flagging (`NFR-AVAIL-01`).
- **Permission matrix** — every role against every endpoint.
- **Load** — 500 concurrent users per campus instance (`NFR-PERF-02`), Phase 7.
- **Security review** — RBAC coverage, encryption in transit/at rest, audit completeness (`NFR-SEC-05`),
  Phase 7.
