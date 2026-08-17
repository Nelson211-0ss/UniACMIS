# UniACMIS — working notes for contributors

University Academic Management Information System for South Sudan. Read
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) before adding a module; this file is the short version of
the rules that file explains.

## Orientation

| Where | What |
|---|---|
| `backend/apps/core` | Infrastructure only. Base models, money types, sync engine, ports, permission class, error shape. **Imports no domain app.** |
| `backend/apps/audit` | Hash-chained append-only trail + the `AuditedModel` mixin |
| `backend/apps/accounts` | `User`, `Role`, and `roles.py` — the whole authorisation policy in one file |
| `backend/apps/academics` | Institution, calendar, grading scale. Data-driven configuration lives here |
| `backend/apps/curriculum` | Faculty → Department → Programme → Course, versioned |
| `backend/apps/registry` | Students and staff. Top of the layering, so it may import everything below |
| `frontend/lib/outbox.ts` | IndexedDB queue. `sync.ts` flushes it |

## Rules that are enforced, not just advised

**Layering.** `registry` → `curriculum` → `academics` → `accounts` → `audit` → `core`. A lower layer never
imports a higher one, and `core` imports no domain app at all. `make lint` runs `lint-imports`, which
fails the build on a violation. When `core` needs domain behaviour it resolves a **port** that the owning
app registers at `AppConfig.ready()` (see `apps/core/ports.py`).

**No cross-app model imports.** Use lazy FK strings (`"curriculum.Programme"`) and call the other module's
`services.py`. If you need a value from another app, add a function there rather than importing its
models — `registry` asks `academics.services.calendar.academic_year_name()` for exactly this reason.

**Every endpoint declares its permission.** `permission_classes = [HasModulePermission]` plus
`required_permission` or `required_permissions`. Use `required_permission = None` for authenticated-only.
`tests/test_permission_matrix.py` fails if a view declares nothing, so an unguarded endpoint cannot ship.

**Configuration is data.** Grading bands, calendar windows, ID formats and thresholds are rows, editable
by staff (`NFR-MAINT-03`). Do not add a constant a registrar would need a developer to change.

**Money carries its currency.** Use `apps.core.fields` — never a bare `DecimalField` for an amount.

## Adding a module (Phase 2 onward)

1. `apps/<module>/` with `models.py`, `services.py` (its public API), `serializers.py`, `views.py`,
   `urls.py`, `admin.py`, `tests/`.
2. Add it to `LOCAL_APPS` **below** the apps it depends on, and to the `layers` contract in
   `pyproject.toml`.
3. Declare its permissions in `apps/accounts/roles.py`. They may already be listed there as pending —
   `seed_roles` starts applying them the moment the module is installed.
4. Add the module and its FR IDs to `docs/TRACEABILITY.md`.
5. Audited models: inherit `AuditedModel`, list `audit_fields`, and set `audit_sensitive = True` for
   anything holding grades or money.
6. Offline-capable writes: register a `SyncHandler` (see `apps/registry/sync.py` for the reference
   implementation). Anything touching marks or money uses `ConflictPolicy.FLAG_FOR_REVIEW`.

## Conventions

- Type hints, `from __future__ import annotations`, docstrings on anything non-obvious.
- Comments explain **why**, not what. The interesting comments here are the ones recording a constraint —
  a wrong device clock, a power cut mid-write, an ID printed on a certificate.
- Services raise `DomainError` subclasses; the exception handler turns them into the standard envelope.
- Never hand-edit a migration. Fix the model and regenerate.
- Tests alongside the code (`apps/<module>/tests/`); cross-module flows in `backend/tests/`.

## Before pushing

```bash
make lint    # ruff, black --check, import-linter
make test    # 234 tests at the end of Phase 1
```

Both run in CI, along with `makemigrations --check`, `check --deploy` against production settings, and a
`seed_roles` idempotency run.

## Things that will bite you

- **`DJANGO_SETTINGS_MODULE` in the environment overrides `pyproject.toml`.** The containers set
  `config.settings.dev` so `runserver` works, so pytest pins its own with `--ds=config.settings.test` in
  `addopts`. Without that the suite runs against dev settings and login tests fail with 429s that look
  like application bugs.
- **The audit chain hashes `created_at`.** It is a `default=timezone.now` field, not `auto_now_add`, because
  `auto_now_add` would overwrite the value after it was hashed and every entry would fail verification.
- **`AuditedModel` snapshots on `pk`, not `_state.adding`.** Django's `from_db()` builds the instance
  before flipping `adding` to False, so `adding` is useless at `__init__` time.
- **Postgres publishes on host port 5433** to coexist with a locally installed PostgreSQL.
- **The service worker only registers in production builds.** The offline outbox works in dev; the cached
  app shell does not.
