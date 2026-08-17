# UniACMIS

**University Academic Management Information System** for universities operating in South Sudan.

Replaces manual and paper-based academic administration across admissions, registry, curriculum,
enrollment, timetabling, attendance, examinations, finance, HR, library, hostel, documents,
communications, alumni and statutory reporting — designed to keep working through the power and
connectivity interruptions that are normal in its operating environment.

> ## Status: Phase 1 (Foundation) — built and passing
>
> Six Django apps (`core`, `audit`, `accounts`, `academics`, `curriculum`, `registry`), a thin PWA shell
> with a working offline outbox, **234 tests green**, three module-boundary contracts enforced, and a
> verifiable audit chain over the seeded data.
>
> Phase 2 (Admissions & Enrollment) has not started. Design docs:
> [ARCHITECTURE.md](docs/ARCHITECTURE.md) · [DATA_MODEL.md](docs/DATA_MODEL.md) ·
> [PHASE1_TASKS.md](docs/PHASE1_TASKS.md) · [TRACEABILITY.md](docs/TRACEABILITY.md)

---

## Why it is built this way

Four constraints drive most of the design, and are worth understanding before reading the code:

- **Intermittent internet.** Attendance, grade entry and library circulation must work with no network and
  sync afterwards. Writes queue in IndexedDB on the client and replay against an idempotent endpoint, so a
  connection that drops mid-sync cannot duplicate or lose records.
- **Intermittent power.** Ungraceful shutdown is routine, so transactions stay short and no workflow keeps
  state on the server between requests.
- **Fraud pressure on grades and money.** Every such write is captured in an append-only, hash-chained
  audit trail, and no single non-ICT role holds both grade-write and money-write permissions.
- **SSP with USD alongside it.** Money is always an amount *plus* a currency, with the FX rate recorded at
  the time — an amount without its rate is not reconstructable later.

Full reasoning in [ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Stack

| Layer | Technology |
|---|---|
| Backend | Django 5.2 LTS · Django REST Framework · SimpleJWT |
| Database | PostgreSQL 16 |
| Frontend | Next.js 15 (App Router) as an installable PWA |
| Offline | Hand-written service worker + IndexedDB outbox (`idb`) |
| Async | Celery + Redis |
| Storage | Local filesystem or MinIO (S3-compatible, no cloud dependency) |
| Docs | OpenAPI 3 via drf-spectacular |
| Quality | pytest · ruff · black · import-linter |

## Requirements

- Docker 24+ and Docker Compose v2+ (verified on Docker 29.5 / Compose v5.1)
- Git

Everything else runs in containers. For running the backend outside Docker you need Python 3.12+ and
PostgreSQL 16; for the frontend, Node 20 is recommended (Node 18.18+ works with the pinned Next 15).

---

## Local development

```bash
git clone https://github.com/Nelson211-0ss/UniACMIS.git
cd UniACMIS
cp .env.example .env          # defaults are fine for local development
make up                       # postgres, redis, backend, celery worker + beat, frontend
make migrate                  # apply migrations
make seed                     # roles, permissions, and demo data (development only)
```

| Service | URL |
|---|---|
| API | http://localhost:8000/api/v1/ |
| Swagger UI | http://localhost:8000/api/v1/schema/swagger-ui/ |
| Django admin | http://localhost:8000/admin/ |
| PWA | http://localhost:3000 |
| Mailpit (dev mail, `--profile dev-extras`) | http://localhost:8025 |
| MinIO console (`--profile storage`) | http://localhost:9001 |

`make seed` creates one account per role. Credentials are printed by the command and all accounts are
flagged `must_change_password`. **`seed_demo` refuses to run when `DEBUG=False`** — it is development data,
never production.

### Common commands

```bash
make up / make down       # start / stop the stack (down keeps the database volume)
make logs                 # tail all services
make migrate              # apply migrations
make migrations           # generate migrations after a model change
make seed                 # seed_roles + seed_demo
make seed-roles           # seed_roles only — production-safe, idempotent
make test                 # full pytest suite with coverage
make test-unit            # unit tests only (fast loop)
make lint                 # ruff + black --check + import-linter
make fmt                  # black + ruff --fix
make shell                # Django shell in the backend container
make psql                 # psql session against the dev database
make verify-audit         # re-walk and verify the audit hash chain
```

---

## Environment variables

Full list with defaults in `.env.example`. The ones that matter:

| Variable | Purpose | Dev default |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | Settings module | `config.settings.dev` |
| `SECRET_KEY` | Django secret — **production boot fails on the default** | dev-only value |
| `DEBUG` | Debug mode | `True` |
| `ALLOWED_HOSTS` | Comma-separated hostnames | `localhost,127.0.0.1` |
| `DATABASE_URL` | Postgres DSN | `postgres://uniacmis:uniacmis@db:5432/uniacmis` |
| `REDIS_URL` | Celery broker and result backend | `redis://redis:6379/0` |
| `TIME_ZONE` | Display timezone (storage is UTC) | `Africa/Juba` |
| `DEFAULT_CURRENCY` / `SECONDARY_CURRENCY` | Currency codes | `SSP` / `USD` |
| `NOTIFICATION_PROVIDER` | Dotted path to the SMS/email provider | `...ConsoleNotificationProvider` |
| `PAYMENT_PROVIDER` | Dotted path to the payment provider | `...MockPaymentProvider` |
| `FILE_STORAGE_BACKEND` | `local` or `minio` | `local` |
| `MAX_UPLOAD_SIZE_MB` | Document vault upload cap | `5` |
| `POSTGRES_HOST_PORT` | Host port the DB publishes on (5433 avoids clashing with a local PostgreSQL) | `5433` |
| `ACCESS_TOKEN_LIFETIME_MINUTES` / `REFRESH_TOKEN_LIFETIME_DAYS` | JWT lifetimes | `30` / `7` |
| `LOGIN_MAX_FAILED_ATTEMPTS` / `LOGIN_LOCKOUT_MINUTES` | Account lockout policy | `5` / `15` |
| `ENABLE_DEMO_HOLD_PROVIDER` | Stub fee-balance hold, so FR-ENR-03 is demonstrable before finance exists. **Production refuses to boot with this on.** | `True` |
| `NEXT_PUBLIC_API_BASE_URL` | API base for the PWA | `http://localhost:8000/api/v1` |

Real SMS and mobile-money credentials are only needed from Phases 6 and 4 respectively; until then the
console and mock providers make those paths fully testable.

---

## Migrations

```bash
make migrations      # generate after model changes
make migrate         # apply
```

- Generated migrations are never hand-edited. If one is wrong, fix the model and regenerate.
- Migrations must be reversible; a data migration ships with its reverse function.
- CI runs `makemigrations --check --dry-run`, so a model change without its migration fails the build.

## Tests

```bash
make test                                          # everything, with coverage
make test-unit                                     # unit only
docker compose exec backend pytest -k grading -q    # a single area
```

Testing is not deferred to the end. From Phase 1 the suite covers GPA and grading-scale logic, student-ID
generation under concurrency, the audit hash chain, the RBAC permission matrix across every role and
endpoint, registration holds through a fake provider, and offline sync replay/duplicate/conflict handling.
See [PHASE1_TASKS.md](docs/PHASE1_TASKS.md) WP11.

### Offline drill (manual, part of Phase 1 acceptance)

1. `make up`, then sign in at http://localhost:3000 as `registrar@demo.uniacmis.ss`.
2. Open **Admit a student** once while online, so programmes and academic years are loaded.
3. DevTools → Network → **Offline**.
4. Submit the form. It reports the entry as **queued on this device — not yet saved**, never as saved,
   and it appears under **Offline queue** (also visible in Application → IndexedDB →
   `uniacmis-outbox`).
5. Restart the browser — the queued entry is still listed.
6. Go back online. The outbox flushes and the student is created exactly once, with the server-issued
   student ID shown against the entry.
7. Re-post the same batch to `POST /api/v1/sync/batch` with the same `client_op_id` values. Every
   operation returns `duplicate` and no second record appears.

> **The service worker only registers in a production build.** In `make up` (dev server) the outbox,
> queueing and replay protection all work — steps 3–7 pass — but the app *shell* is not cached, so a
> hard reload while offline will not render. To exercise that too, build the frontend for production
> (`docker compose build frontend --target prod`). Registering a caching worker in front of the dev
> server produces stale pages that look like application bugs, which is why it is disabled there.

---

## Project layout

```
UniACMIS/
├── backend/
│   ├── config/              # settings/{base,dev,test,prod,build}, urls, celery
│   ├── apps/
│   │   ├── core/            # base models, MoneyField, sync engine, providers, error shape
│   │   ├── accounts/        # User, Role, RBAC registry, JWT
│   │   ├── audit/           # hash-chained append-only audit log
│   │   ├── academics/       # institution, calendar, grading scales, GPA
│   │   ├── curriculum/      # faculty → department → programme → course
│   │   └── registry/        # students, staff, documents, status history
│   ├── conftest.py          # shared fixtures (at the root, so app tests share them)
│   └── tests/               # cross-module integration tests
├── frontend/                # Next.js PWA: app/, lib/{api,auth,outbox,sync}, public/sw.js
├── docs/                    # architecture, data model, tasks, traceability
├── docker-compose.yml
└── Makefile
```

Modules do not import each other's models — they call each other through `services.py` and a provider
registry, and `import-linter` enforces it in CI. Adding a module: [ARCHITECTURE.md §4](docs/ARCHITECTURE.md).

---

## Deployment

Primary deployment is **one instance per campus, on premise**, with a central instance used for backup and
cross-campus reporting rather than as the system of record — the campus must keep operating with no
internet at all. Topology in [ARCHITECTURE.md §11](docs/ARCHITECTURE.md).

Production checklist (details in `docs/DEPLOYMENT.md`, added in Phase 7):

- [ ] `DEBUG=False`, a real `SECRET_KEY`, `ALLOWED_HOSTS` set
- [ ] HTTPS terminated at nginx; HSTS enabled
- [ ] Application DB role has no `UPDATE`/`DELETE` grant on `audit_auditlog`
- [ ] Nightly `pg_dump` retained locally, replicated off-site when bandwidth allows, **restore rehearsed**
- [ ] UPS/solar at the server and at registrar/finance terminals
- [ ] `make seed-roles` run on deploy; `seed_demo` never run
- [ ] Real `NotificationProvider` and `PaymentProvider` configured

## Documentation

| Document | Contents |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Modular monolith, module boundaries, audit/RBAC/sync contracts, provider interfaces, deployment |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | Phase 1 entities, relationships, invariants, ID generation |
| [docs/PHASE1_TASKS.md](docs/PHASE1_TASKS.md) | Work packages with acceptance criteria |
| [docs/TRACEABILITY.md](docs/TRACEABILITY.md) | Every FR/NFR → phase and status, deferrals, open items |

Requirements baseline: `ACMIS_System_Requirements_Specification.docx` and
`ACMIS_Workflow_Checklist.docx`. Seven open items need confirmation from the university or MoHEST before
the requirements they block can be completed — listed at the end of TRACEABILITY.md.
