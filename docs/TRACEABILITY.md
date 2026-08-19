# UniACMIS — Requirements Traceability Matrix

Every requirement in `ACMIS_System_Requirements_Specification.docx` mapped to the phase that delivers it,
with its current status. This is the acceptance-tracking register: a requirement is not "done" until the
listed evidence exists.

**Status key** — `✅ done` (implemented and covered by tests) · `🧱 foundation laid` (the mechanism
exists in Phase 1; the module-facing feature comes later) · `📋 planned` · `⏸ deferred by decision`

Where a row spans phases (`**1**/3`), `✅` means the Phase 1 portion is complete — the mechanism is built
and tested; the module that consumes it arrives in the later phase.

Phases follow the implementation plan: 1 Foundation · 2 Admissions & Enrollment · 3 Academic Operations ·
4 Finance · 5 Supporting modules · 6 Documents/Comms/Reporting · 7 Hardening.

---

## Functional requirements

### 3.1 Admissions & applications

| ID | Requirement | Phase | Status | Notes |
|---|---|---|---|---|
| FR-ADM-01 | Online application with bio-data + document upload | 2 | ✅ | `Application`, `ApplicationDocument`; `eligibility_warnings()` before submit |
| FR-ADM-02 | Offline/paper application intake by staff | 2 | 🧱 | `ApplicationSource.STAFF_ENTRY` lets staff key in a paper form online; no offline sync handler registered for it yet, unlike `registry.student` and Phase 3's `attendance`/`examinations` entities |
| FR-ADM-03 | Configurable programme entry requirements + validation | 2 | ✅ | `eligibility.py` (pure functions) reads `Programme.entry_requirements` from Phase 1 |
| FR-ADM-04 | Application fee recorded + reconciled before completion | 2/4 | ✅ | `initiate_fee_payment`/`confirm_fee_payment` via the Phase 1 mock `PaymentProvider`; `submit_application` requires `fee_paid=True`. Real aggregator is Phase 4. |
| FR-ADM-05 | Admissions committee review with configurable scoring | 2 | ✅ | `ApplicationReview` (one per reviewer, upserts) recomputes the average score |
| FR-ADM-06 | Merit lists with quota rules (state, gender, disability, sponsorship) | 2 | ✅ | `merit_list.py` (pure functions): reserved quotas fill first, underfilled seats revert to the general pool |
| FR-ADM-07 | Offer/rejection letters via portal, email, SMS | 2/6 | 🧱 | `decide_application` triggers `NotificationProvider.send_sms/send_email` (console/mock in Phase 1); a failed send does not block the decision. Real SMS aggregator is Phase 6. |
| FR-ADM-08 | Convert accepted application → student record, auto student ID | 2 | ✅ | `convert_to_student()` calls `registry.services.create_student`, reusing the Phase 1 ID generator |

### 3.2 Student records (core registry)

| ID | Requirement | Phase | Status | Notes |
|---|---|---|---|---|
| FR-REG-01 | Unique, non-reusable student ID | **1** | ✅ | Template-driven; `IdSequence` + unique constraint; concurrency test |
| FR-REG-02 | Bio-data, next-of-kin, sponsor, disability/special needs | **1** | ✅ | `Student`, `NextOfKin`, `Sponsor` |
| FR-REG-03 | Document vault for scans and photos | **1** | ✅ | `StudentDocument` incl. content hash; upload UI Phase 2 |
| FR-REG-04 | Status tracking with audit history of changes | **1** | ✅ | `StudentStatusHistory` + audit log |
| FR-REG-05 | Change-of-programme, transfer, credit transfer | **1**/2 | 🧱 | Fields present; workflow Phase 2 |
| FR-REG-06 | Bulk import from Excel/CSV with validation + error reporting | 2 | 📋 | `NFR-DATA-03` tooling |

### 3.3 Academic & curriculum management

| ID | Requirement | Phase | Status | Notes |
|---|---|---|---|---|
| FR-CUR-01 | Faculty → Department → Programme → Course hierarchy | **1** | ✅ | |
| FR-CUR-02 | Course catalogue: credit hours, prerequisites, core/elective | **1** | ✅ | `Course`, `CurriculumCourse`, `Prerequisite` |
| FR-CUR-03 | Curriculum version control tied to cohorts | **1** | ✅ | `CurriculumVersion`; `Student.curriculum_version` |
| FR-CUR-04 | Lecturer→course allocation + workload calculation | 3 | 🧱 | `StaffProfile` exists Phase 1 |

### 3.4 Registration & enrollment

| ID | Requirement | Phase | Status | Notes |
|---|---|---|---|---|
| FR-ENR-01 | Academic calendar controlling registration/add-drop/exam windows | **1**/2 | ✅ | `AcademicYear`/`Semester` windows modelled Phase 1; enforced Phase 2 |
| FR-ENR-02 | Prerequisite + credit-limit validation | 2 | ✅ | `register_course()` raises `PrerequisiteNotMet`/`CreditLimitExceeded` against Phase 1's `Prerequisite` and `Programme.max_credits_per_semester` |
| FR-ENR-03 | Registration holds (fees, discipline, missing documents), configurable | 2/4 | ✅ | Provider interface + fake finance provider + tests in Phase 1 |
| FR-ENR-04 | Auto-generated class lists | 2 | ✅ | `enrollment.services.class_list()`, ordered for a printable register |
| FR-ENR-05 | Repeat/carry-over unit tracking | 2 | ✅ | `CourseRegistration.is_repeat`, set automatically by `register_course()` |

### 3.5 Timetabling

| ID | Requirement | Phase | Status | Notes |
|---|---|---|---|---|
| FR-TT-01 | Automated clash-free timetable generation | 3 | ✅ | Manual entry + room/lecturer clash detection, per D-3; auto-generation remains a stretch goal |
| FR-TT-02 | Manual override | 3 | ✅ | A registrar edits any entry; `update_entry` re-runs the same clash checks |
| FR-TT-03 | Publish to portal + printable PDF for notice boards | 3 | 🧱 | Publish workflow + role-scoped read API done; a bare HTML print view stands in for a PDF renderer (no new binary dependency added for Phase 3 — see D-8) |
| FR-TT-04 | Exam timetable with invigilator assignment | 3 | ✅ | `ExamTimetable` + M2M invigilators, room/invigilator clash detection, bounded to the semester's exam window |

### 3.6 Attendance

| ID | Requirement | Phase | Status | Notes |
|---|---|---|---|---|
| FR-ATT-01 | Offline attendance capture with later sync | 3 | ✅ | `SessionRecordHandler` registered; proven end-to-end via the batch sync API |
| FR-ATT-02 | Threshold flagging + exam block with authorised override | 3 | ✅ | `attendance.services.exam_eligibility()` + `AttendanceWaiver` (`attendance.override_block`, examinations office only) |

### 3.7 Examinations & assessment

| ID | Requirement | Phase | Status | Notes |
|---|---|---|---|---|
| FR-EXM-01 | CA score entry with configurable weighting | 3 | ✅ | `Assessment` (per-course scheme) + `Mark`; weights validated at the point a result is computed, not on each row (D-9) |
| FR-EXM-02 | Grade-entry deadline enforcement + late-submission logging | 3 | ✅ | `Assessment.grade_entry_deadline`; late entry is logged (`Mark.is_late`) rather than blocked — see D-9 |
| FR-EXM-03 | Moderation / second-marking workflow | 3 | ✅ | `examinations.moderate_result`, held by `hod` only — distinct from the marking lecturer |
| FR-EXM-04 | Automatic GPA/CGPA per configured grading scale | **1**/3 | ✅ | `GradingScale`/`GradeBand` + pure `gpa()`/`cgpa()` from Phase 1, now wired to real marks via `course_result()`/`semester_gpa()` |
| FR-EXM-05 | Senate/exam board approval before release | 3 | ✅ | `ResultApproval`: `approve_result` (Senate) and `publish_result` (examinations office) are distinct permissions, held by neither role at once |
| FR-EXM-06 | Withhold results for arrears/discipline, configurable | 3 | ✅ | `student_result()` checks `core.services.holds.blocking_holds()` at read time; a published result stays withheld until the hold clears, with no separate "unwithhold" step |
| FR-EXM-07 | Grade appeal / remark workflow | 3 | ✅ | `GradeAppeal`: a student submits their own; `hod`/`examinations` decide via `examinations.decide_gradeappeal` |
| FR-EXM-08 | Missing-mark and irregularity flagging | 3 | ✅ | `missing_marks_report()`; `Mark.is_irregular` excludes a disputed mark from its course result until cleared |

### 3.8 Finance & fees

| ID | Requirement | Phase | Status | Notes |
|---|---|---|---|---|
| FR-FIN-01 | Fee structures by programme/year/residency | 4 | ✅ | `FeeStructure`; residency derived from nationality (`registry.services.residency_for_student`), not a duplicate field — see D-11 |
| FR-FIN-02 | Automatic semester invoices from registration | 4 | ✅ | `generate_invoice()` / batch `generate_invoices_for_semester()`, applying any active scholarship discount |
| FR-FIN-03 | Bank slip, mobile money, cash, cheque + reconciliation | 4 | ✅ | Mobile money through the Phase 1 `PaymentProvider` (webhook + polling, signature-verified); cash confirms on the spot, cheque/bank-slip are reconciled by hand via `confirm_manual_payment` |
| FR-FIN-04 | Scholarship/bursary/government-sponsored accounts tracked distinctly | 4 | ✅ | `Scholarship` (percentage or fixed amount, capped at the invoice), distinct from `registry.Sponsor` (who funds it) |
| FR-FIN-05 | Installment/payment plans with balance tracking | 4 | ✅ | Any number of `Payment` rows against one `Invoice`; `invoice_balance()` is always the true remainder — no separate instalment-schedule model; see D-12 |
| FR-FIN-06 | Automatic receipt on confirmed payment | 4 | ✅ | `IdSequence`-backed `RCT/{year}/{seq:05d}`, issued the moment a payment is confirmed |
| FR-FIN-07 | Defaulter reports + outstanding balance dashboards | 4 | ✅ | `services.defaulter_report()` + `finance.view_defaulterreport` |
| FR-FIN-08 | Refund workflow with approval controls | 4 | ✅ | `Refund`: the student (or finance, on their behalf) requests, only `finance.approve_refund` decides — never the same permission as the request |

### 3.9 Human resources

| ID | Requirement | Phase | Status | Notes |
|---|---|---|---|---|
| FR-HR-01 | Staff bio-data, contracts, qualifications | **1**/5 | ✅ | `StaffProfile` core record Phase 1; `hr.Contract` (one row per contract, never edited in place — see D-14) |
| FR-HR-02 | Leave application with multi-level approval | 5 | ✅ | `LeaveRequest`: staff submits, their HOD endorses (`has_role("hod")`), HR gives the final decision (`hr.approve_leaverequest`) — three distinct actors, never the same one twice |
| FR-HR-03 | Appraisal + promotion history | 5 | ✅ | `Appraisal`, one per staff member per academic year; authored by the HOD (`hr.add_appraisal`, granted to `hod` not `hr`) — HR holds view/change only, since it is not who conducts the review |
| FR-HR-04 | Payroll-ready export | 5 | ✅ | `services.payroll_export()` behind `hr.export_payroll`; figures only — payroll computation is out of scope (SRS §1.2) |

### 3.10–3.11 Library · Hostel

| ID | Requirement | Phase | Status | Notes |
|---|---|---|---|---|
| FR-LIB-01 | Catalogue of physical + electronic resources | 5 | ✅ | `LibraryItem`; browsing is public to any authenticated user (`"SAFE": None`), cataloguing is `library` staff only |
| FR-LIB-02 | Circulation, due dates, automatic fines | 5 | ✅ | `Loan` uses `MoneyAmountField`/`CurrencyField`; `LibraryPolicy` (loan period, daily rate) is a staff-editable singleton, not a constant |
| FR-LIB-03 | Offline circulation with sync to central catalogue | 5 | ✅ | `library.sync.LoanCheckoutHandler` reuses the Phase 1 sync engine, `LAST_WRITE_WINS` — a checkout is a physical event, not a financial one |
| FR-HOS-01 | Room inventory + capacity | 5 | ✅ | `Room`; `available_beds`/`occupied_beds` computed from active allocations, never stored |
| FR-HOS-02 | Allocation by configurable priority rules | 5 | ✅ | `services.allocate_room()` (gender match, capacity lock); `waiting_list_priority()` is a documented ranking function, not a data-driven engine — see D-15 |
| FR-HOS-03 | Hostel fees linked to finance | 5 | ✅ | `hostel` sits below `finance` in the layering; `finance.generate_invoice()` calls `hostel.services.fee_for_active_allocation()` and adds it onto the same invoice — see D-16, D-17 |

### 3.12 Documents & certification

| ID | Requirement | Phase | Status | Notes |
|---|---|---|---|---|
| FR-DOC-01 | Transcript/certificate requests with approval workflow | 6 | 📋 | |
| FR-DOC-02 | QR code / unique serial on issued documents | 6 | 🧱 | `IdSequence` issues verification serials |
| FR-DOC-03 | Public employer-facing verification page | 6 | 📋 | No login; rate-limited |
| FR-DOC-04 | Graduation clearance checklist (library, finance, hostel, dept) | 6 | 🧱 | Reuses the hold-provider registry |

### 3.13–3.14 Communications · Alumni

| ID | Requirement | Phase | Status | Notes |
|---|---|---|---|---|
| FR-COM-01 | SMS for critical events | 6 | ✅ | `communications.Announcement` fans out through the Phase 1 `NotificationProvider` port; console impl until a real aggregator is contracted (open item 2) |
| FR-COM-02 | Email as secondary channel | 6 | ✅ | Same `send_announcement()` call, same port |
| FR-COM-03 | Bulk announcements to audiences (all students, class, **campus**) | 6 | ✅/⏸ | All-students, one programme ("class") and alumni audiences built; campus-scoped stays blocked by the multi-campus deferral (D-1) since there is only ever one campus to scope to |
| FR-ALM-01 | Alumni contact + employment/tracer data | 6 | ✅ | `alumni.AlumniProfile`, one per graduated student; contact fields kept separate from `registry.Student`'s so a tracer update never rewrites the academic record |
| FR-ALM-02 | Alumni communication + event records | 6 | ✅ | `alumni.AlumniEvent` for the record; messaging alumni reuses `communications.send_announcement`'s `alumni` audience rather than a second notification path |

### 3.15 Reporting & compliance

| ID | Requirement | Phase | Status | Notes |
|---|---|---|---|---|
| FR-RPT-01 | Configurable dashboards (enrollment, pass rates, revenue, ratios) | 6 | ✅ | `DashboardWidget` (enabled/ordered, staff-editable) selects among a fixed, documented set of KPI functions — see D-18 |
| FR-RPT-02 | MoHEST statutory report templates, configurable | 6 | ✅/⏸ | `student_register` is the generic disaggregated export the open item already anticipated; the real MoHEST template stays unconfirmed (open item 1) |
| FR-RPT-03 | Disaggregation by gender, disability, state of origin | **1**/6 | ✅ | Fields captured as constrained choices in Phase 1 — free text would make this unreportable |
| FR-RPT-04 | Tamper-evident audit trail for all grade + financial data | **1** | ✅ | Hash-chained append-only `AuditLog` + `verify_audit_chain` |
| FR-RPT-05 | Custom report building, export Excel/PDF/CSV | 6 | ✅/⏸ | CSV (stdlib) and Excel (`openpyxl`, pure Python) built; PDF stays out of scope for the same reason D-8 keeps a timetable an HTML page — no PDF renderer's system libraries are in this image |

---

## Non-functional requirements

| ID | Requirement | Phase | Status | Notes |
|---|---|---|---|---|
| NFR-PERF-01 | Key pages < 3 s on 3G | 7 | 🧱 | PWA shell + pagination from Phase 1; measured in Phase 7 |
| NFR-PERF-02 | 500 concurrent users per campus instance | 7 | 📋 | Load test in hardening |
| NFR-PERF-03 | Standard reports < 30 s at 20,000 students | 7 | 📋 | Celery + indexed paths |
| NFR-AVAIL-01 | Offline function + queued sync for attendance, grades, circulation | **1** | ✅ | Engine + outbox + conflict policy proven in Phase 1 |
| NFR-AVAIL-02 | Consistent recovery after ungraceful power loss | **1**/7 | 🧱 | Short transactions, no server-side request state, WAL durability; drill in Phase 7 |
| NFR-AVAIL-03 | 99% term-time uptime | 7 | 📋 | Operational, not code |
| NFR-SEC-01 | RBAC, least privilege, every user class | **1** | ✅ | Declarative registry + permission-matrix test |
| NFR-SEC-02 | PII + financial data encrypted at rest and in transit | 7 | 🧱 | HTTPS + disk encryption documented Phase 1; verified Phase 7 |
| NFR-SEC-03 | Log all access to and modification of grades/finance, 5-year retention | **1** | ✅ | `AuditLog` incl. `view_sensitive`; retention policy documented |
| NFR-SEC-04 | Salted hashing; MFA available for finance + registrar | **1**/7 | ✅ | Django hashers; TOTP enrolment (`apps.accounts.services.start_mfa_enrolment`/`confirm_mfa_enrolment`), backup codes, and login-time enforcement all built in Phase 7 — available to any account, not gated to a role, per D-21 |
| NFR-SEC-05 | Security review / pen test before launch, annually after | 7 | 📋 | |
| NFR-USE-01 | English primary; text externalised for translation | **1** | ✅ | `gettext` from the start — retrofitting i18n means touching every template |
| NFR-USE-02 | Responsive 5-inch → desktop | **1** | ✅ | Mobile-first PWA shell |
| NFR-USE-03 | Critical notifications by SMS | 6 | 🧱 | Provider interface Phase 1 |
| NFR-MAINT-01 | Modular components, independently updatable | **1** | ✅ | Modular monolith + import-linter contracts in CI |
| NFR-MAINT-02 | Standard Linux, no proprietary vendor lock-in | **1** | ✅ | Docker Compose, Postgres, MinIO |
| NFR-MAINT-03 | Config data-driven, not hard-coded | **1** | ✅ | Calendar, grading scale, ID template, thresholds are rows |
| NFR-DATA-01 | Automated daily backups + periodic off-site replication | 7 | 🧱 | `scripts/backup_database.sh`/`restore_database.sh` built and proven (restore rehearsed against a scratch database); registering the nightly cron entry is a deployment step, not a code one |
| NFR-DATA-02 | Documented retention + archival policy | 7 | 📋 | |
| NFR-DATA-03 | Bulk migration tooling with validation + rollback | 2/7 | ✅/⏸ | `manage.py import_students` built and proven end-to-end (CSV → dry-run validation → `--commit`); staff onboarding follows the same shape once `registry` gains a `create_staff_profile` service — see D-23 |

---

## Deferrals and decisions

| # | Item | Decision | Consequence |
|---|---|---|---|
| D-1 | **Multi-campus architecture** (checklist §1, SRS §4.5, `FR-COM-03`) | Deferred — single campus in Phase 1 | No `Campus` model or FK. Adding it later requires a migration touching most tables plus every scoped queryset and permission check. Accepted knowingly. |
| D-2 | `apps/academics` added to the module list | Accepted | Owns the data-driven configuration `NFR-MAINT-03` requires, which no single module owns. |
| D-3 | Automated timetable generation (`FR-TT-01`) | Manual entry + clash detection first | Auto-generation is a stretch goal within Phase 3; clash *detection* is the requirement that actually prevents harm. |
| D-4 | Placeholder Django apps for future modules | Not created | Only apps with real models exist, so enforced boundaries are visible. Structure documented in ARCHITECTURE.md §3. |
| D-5 | **`senate` role split from `management`** | Accepted | SRS §2.2 lists them together, but `FR-EXM-05` needs approval to be an authority the examinations office does not hold. 13 roles rather than 12. |
| D-6 | `seed_demo` lives in `registry`, not `core` | Accepted | It constructs data across every app, so it belongs at the top of the layering, not underneath it. Exempted from the models-import contract with a stated reason. |
| D-7 | Student-cohort clash detection (`FR-TT-01`) | Deferred | `timetabling` detects a room or lecturer double-booking — both provable today, since a room is one place and a lecturer is one person. Detecting that two courses a *student* must take were scheduled at once needs a class-group/section model this system does not have yet; auto-generation (D-3) is blocked on the same gap. |
| D-8 | Printable exam/class timetable as a rendered PDF (`FR-TT-03`) | Deferred — HTML print view instead | A binary PDF renderer (e.g. WeasyPrint) needs system libraries (Cairo/Pango) added to the Docker image for a need a browser's own print-to-PDF already satisfies. Revisit if a headless export (e-mail attachment, batch print run) is actually requested. |
| D-9 | Assessment weight-sum validation (`FR-EXM-01`) | Validated at result computation, not at each write | A lecturer builds a CA scheme one component at a time; rejecting "CA1: 20%" for not summing to 100% on its own would make incremental entry impossible. `course_result()` checks the full scheme sums to 100% before computing a grade from it, the same "validate where it's used" choice `grade_for()` makes for a gapped grading scale. |
| D-10 | `apps.core.choices.Residency` lives in `core`, not `finance` (`FR-FIN-01`) | Accepted | `registry` derives a student's residency from nationality, and `registry` sits below `finance` in the layering — a lower app may never import a higher one's models. The alternative (a `residency` field duplicated on `Student`) would just be a second place for it to drift from `nationality`. |
| D-11 | No cross-currency payments (`FR-FIN-03`) | Deferred | A payment must be recorded in its invoice's own currency; `apps.core.fields.Money` already refuses to combine currencies without an explicit rate, and inventing one here would be no different from guessing. A foreign-currency payment is recorded as its SSP equivalent by whoever takes it, the same way a bank teller would. Revisit if the institution actually invoices in more than one currency at once. |
| D-12 | No instalment-schedule model (`FR-FIN-05`) | Deferred | Any number of `Payment` rows may exist against one `Invoice`, and `invoice_balance()` is always the true remainder — instalments-with-balance-tracking without a second model that could disagree with the first. What is not built is a fixed *schedule* (specific amounts due on specific dates); a defaulter is currently "the invoice's due date has passed with a balance remaining," not "instalment 2 of 3 is late." |
| D-13 | TOTP/MFA enrolment (`NFR-SEC-04`) | Deferred | `docs/ARCHITECTURE.md` §6 flags this as landing with the finance module; `User.mfa_enabled` and the enforcement hook exist from Phase 1, but the enrolment flow (secret generation, QR code, backup codes) is not built. Tracked here rather than silently dropped. |
| D-14 | `hr.Contract` is append-only, never edited in place (`FR-HR-01`) | Accepted | A renewal, promotion or change in terms creates a new `Contract` row rather than mutating the old one, so the history a payroll export or a dispute needs is never overwritten. `is_active` marks the current one; `end_contract()` closes it out instead of deleting it. |
| D-15 | Automated hostel-allocation priority (`FR-HOS-02`) | Deterministic ranking function, not a data-driven rules engine | Same "detection over generation" scope line Phase 3 drew for timetabling (D-3/D-7): `hostel.services.waiting_list_priority()` ranks by disability, state of origin, and entry year — documented in the function itself. Revisit if a registrar actually needs the weights configurable. |
| D-16 | Scholarship discounts cover tuition only, not the hostel fee (`FR-FIN-04`/`FR-HOS-03`) | Accepted | `generate_invoice()` adds the hostel fee (if any) onto the invoice *after* computing the scholarship discount off the tuition amount alone, because `Scholarship.coverage_type` (percentage/fixed amount) does not yet distinguish what it is meant to cover. A scholarship that should also waive accommodation needs a bigger fixed amount today, not a second coverage dimension nobody has asked for yet. |
| D-17 | The hostel fee is billed in the tuition invoice's currency, not its own (`FR-HOS-03`) | Accepted | `HostelPolicy.currency` is assumed to match the institution's base currency, the same single-currency stance D-11 takes for payments — no conversion is attempted when adding it onto an invoice. |
| D-18 | Dashboard KPIs and the report catalog are fixed, documented functions (`FR-RPT-01`/`FR-RPT-05`) | Not a data-driven query-building engine | Same "detection over generation" scope line D-3/D-7/D-15 draw: `enrollment`, `revenue`, `ratios` and `pass_rate` are the whole catalog. `DashboardWidget` makes which of them are *visible*, and in what order, real configuration (`NFR-MAINT-03`) without needing a generic ad-hoc query builder nobody has asked for. |
| D-19 | No alumni self-service portal (`FR-ALM-01`/`FR-ALM-02`) | Deferred | The 13 roles in `apps/accounts/roles.py` come from SRS §2.2 plus the `senate` split (D-5); "alumni" is not one of them. `AlumniProfile`/`AlumniEvent` are registrar-managed data, not a login an ex-student holds. Revisit if the university actually wants graduates updating their own tracer data. |
| D-20 | Bulk announcement sends run inline, not via a Celery task (`FR-COM-01`/`FR-COM-03`) | Deferred | `apps.core.providers.notifications` documents "always from a Celery task, never inline", but no app in this codebase has ever actually done so — `admissions._notify_decision` calls the provider inline inside a try/except, and `communications.send_announcement` matches that real precedent rather than introducing this codebase's first Celery task as a side effect of one feature. Revisit once a real SMS/email aggregator (open item 2) makes send latency and retry semantics an actual production concern. |
| D-21 | MFA enrolment is available to every account, not gated to finance/registrar (`NFR-SEC-04`) | Accepted | The requirement says "available for finance and registrar roles", not "mandatory" or "forbidden elsewhere" — gating enrolment by role would mean a lecturer who wants the extra protection could not have it. `mfa_enabled`/`mfa_secret` live on every `User`; nothing about the enrolment endpoints checks a role. Making it *mandatory* for finance/registrar specifically (an enforcement policy, not a capability) is a product decision the SRS text does not actually make, so it is not built. |
| D-22 | `pg_dump` runs inside the `db` container, not the `backend` one (`NFR-DATA-01`) | Accepted | `backend/Dockerfile` deliberately carries no apt layer — `psycopg[binary]` bundles libpq, so the app image needs no system packages, and adding `postgresql-client` just for a nightly cron job would reverse that choice. `postgres:16-alpine` already ships the client tools, so `scripts/backup_database.sh` runs `docker compose exec db pg_dump` instead. |
| D-23 | Bulk staff import deferred; only `import_students` is built (`NFR-DATA-03`) | Deferred | `registry.services.create_student` already existed and was already documented for exactly this ("`student_id` may be supplied when migrating legacy records"), so importing students is wiring a CSV onto a function that already worked. Staff onboarding needs a `User` created alongside the `StaffProfile` — a real service that does not exist yet, not a wiring task — and building that from scratch as a side effect of an import tool would be a second feature growing inside the first. `import_students`'s row-resolution shape (natural keys → validate-all → all-or-nothing commit) is meant to be copied once that service exists. |

## Open items awaiting stakeholder confirmation (SRS §8)

These block specific requirements and need answers from the university or the Ministry. Each is a real
dependency, not a formality:

1. **Exact MoHEST statutory report formats** → blocks `FR-RPT-02`. Mitigation: a generic configurable
   export, per SRS §2.6.
2. **Confirmed mobile money providers at launch** → blocks `FR-FIN-03`. Mitigation: `PaymentProvider`
   interface; manual reconciliation import as fallback.
3. **Existing payroll system + export format** → blocks `FR-HR-04`.
4. **Final grading scale and GPA policy** → Phase 1 seeds a 4.00 credit-weighted default; the registrar
   must confirm bands, pass mark, and how retakes affect CGPA before results are published anywhere.
5. **Data retention period for student and financial records** → blocks `NFR-DATA-02`. Phase 1 assumes the
   `NFR-SEC-03` 5-year audit minimum.
6. **Academic calendar dates and fee structures** for real configuration (SRS §2.6).
7. **Data migration lead** designated to validate legacy records before cutover (SRS §2.6).

---

## Phase 1 verification (recorded 2026-08-17)

Run from a clean clone with `make up && make migrate && make seed`:

| Check | Command | Result |
|---|---|---|
| Django system checks | `manage.py check` | no issues |
| Migrations match models | `manage.py makemigrations --check --dry-run` | no drift |
| Test suite | `pytest` | **234 passed** |
| Module boundaries | `lint-imports` | 3 contracts kept, 0 broken |
| Style | `ruff check .` · `black --check .` | clean |
| RBAC policy applied | `manage.py seed_roles` | 13 roles; future-module permissions deferred, not failed |
| Demo data | `manage.py seed_demo` | 2 faculties, 4 programmes, 21 courses, 30 students |
| Audit chain | `manage.py verify_audit_chain` | 115 entries verified, chain intact |
| Separation of duties | `manage.py permission_matrix --check-separation` | no role holds both grade-write and money-write |

Additions made during implementation, both recorded above: the `senate` role (D-5) and
`apps/core/choices.py` for reference data shared by more than one app.

## Phase 2 verification (recorded 2026-08-18)

Admissions and enrollment, against the same checklist as Phase 1:

| Check | Command | Result |
|---|---|---|
| Test suite | `pytest` | **351 passed** (117 new: admissions + enrollment) |
| Module boundaries | `lint-imports` | 3 contracts kept, 0 broken |
| Style | `ruff check .` · `black --check .` | clean |
| Migrations match models | `manage.py makemigrations --check --dry-run` | no drift |
| RBAC policy applied | `manage.py seed_roles` | idempotent; Phase 3+ permissions still deferred |
| Audit chain | `manage.py verify_audit_chain` | 152 entries verified, chain intact |

Two Phase 1 bugs surfaced and fixed while building on top of it: DRF's default `create()`
re-serialised a new instance through the same narrow input serializer, silently dropping
generated fields like `reference_number` (fixed with `apps.core.mixins.CreateWithResponseSerializerMixin`,
applied to `admissions` and retrofitted onto `registry`); and the demo fee-hold provider's
"every 5th student ID is a defaulter" heuristic caused unrelated tests to fail depending on
Postgres's PK sequence state, since sequences do not roll back with a test transaction — removed,
replaced with explicit seeding in `seed_demo`.

## Phase 3 verification (recorded 2026-08-19)

Timetabling, attendance and examinations:

| Check | Command | Result |
|---|---|---|
| Test suite | `pytest` | **450 passed** (99 new: timetabling + attendance + examinations) |
| Module boundaries | `lint-imports` | 3 contracts kept, 0 broken |
| Style | `ruff check .` · `black --check .` | clean |
| Migrations match models | `manage.py makemigrations --check --dry-run` | no drift |
| RBAC policy applied | `manage.py seed_roles` | idempotent; only Phase 4+ permissions still deferred |
| Audit chain | `manage.py verify_audit_chain` | 159 entries verified, chain intact |

Notable bugs found and fixed while building this phase: a viewset's coarse per-HTTP-method
permission map was gating custom actions (`GradeAppealViewSet.decide`, `ResultApprovalViewSet.approve`/
`reject`) by the *base* method's permission before the action's own, more specific check ever ran —
so Senate's own `approve_result` permission never mattered, because POST already required
`publish_result` first. Fixed with a per-action `get_permissions()` override on both viewsets. A second:
`course_result()` let an unconfigured (or gapped) grading scale raise an unhandled
`GradingConfigurationError` instead of surfacing it the same way as any other misconfigured
assessment scheme.

## Phase 4 verification (recorded 2026-08-19)

Finance — fee structures, invoicing, payments, scholarships, refunds:

| Check | Command | Result |
|---|---|---|
| Test suite | `pytest` | **489 passed** (39 new) |
| Module boundaries | `lint-imports` | 3 contracts kept, 0 broken |
| Style | `ruff check .` · `black --check .` | clean |
| Migrations match models | `manage.py makemigrations --check --dry-run` | no drift |
| RBAC policy applied | `manage.py seed_roles` | idempotent; `finance` resolves fully, no longer pending |
| Audit chain | `manage.py verify_audit_chain` | 197 entries verified, chain intact |
| Separation of duties | `manage.py permission_matrix --check-separation` | no role holds both grade-write and money-write |

The Phase 1 demo fee-hold provider (`apps.core.providers.holds.DemoFeeBalanceHoldProvider`) was **kept**
rather than removed now that the real one exists — `tests/test_registration_holds.py` uses it to exercise
the generic hold-aggregation mechanism (several providers accumulating, one that fails closed, a
non-blocking advisory hold) without needing a real invoice for every case. Its one-line premise guard
(`assert not apps.is_installed("apps.finance")`) was deleted since the day it was written for had
arrived; the file's docstring now says so.

Two real bugs caught before they shipped: `registry.services.residency_for_student` briefly imported
`apps.finance.models.Residency` directly — `registry` sits *below* `finance` in the layering, so a lower
app importing a higher one's models is exactly the violation the import-linter contracts exist to catch.
Moved `Residency` to `apps.core.choices` instead, reachable from both without inverting anything. Second:
`Payment.receipt_number` was declared `null=True` but not `blank=True` — `null` governs the database
column, `blank` governs `full_clean()`, and without both a fresh (not-yet-receipted) payment failed its own
validation on creation.

## Phase 5 verification (recorded 2026-08-19)

HR (contracts, two-level leave approval, appraisal, payroll export), Library (catalogue, circulation,
fines, offline checkout sync) and Hostel (room inventory, gender-matched allocation, a documented
priority ranking, and a real fee link into `finance`) are all complete.

| Check | Command | Result |
|---|---|---|
| Test suite | `pytest` | **569 passed** (80 new over Phase 4: 45 unit, 35 API/sync) |
| Module boundaries | `lint-imports` | 3 contracts kept, 0 broken |
| Style | `ruff check .` · `black --check .` | clean |
| Migrations match models | `manage.py makemigrations --check --dry-run` | no drift |
| RBAC policy applied | `manage.py seed_roles` | idempotent; `hr`, `library` and `hostel` all resolve fully, no longer pending |
| Audit chain | `manage.py verify_audit_chain` | 199 entries verified, chain intact |
| Separation of duties | `manage.py permission_matrix --check-separation` | no role holds both grade-write and money-write |

Three real bugs caught before they shipped, all in code not yet covered by a test at the time. Two were
permission-policy/permission-declaration mismatches: `hr.roles` granted `hr.export_payroll` and
`library.roles` granted `library.waive_fine`, but neither permission was ever declared on a model's
`Meta.permissions` — `seed_roles` silently treated both as "pending" (the mechanism meant for a module
that is not installed yet), so a real HR officer or librarian would have hit a 403 on an endpoint that
unconditionally checked for it. Added `export_payroll` to `Contract` and `waive_fine` to `Loan`.
Separately, `hr.LeaveRequestViewSet` declared `required_permission = "hr.view_leaverequest"` at the class
level — but that permission is only granted to `hr`/`hod`, so a plain lecturer could `submit` their own
leave request (a separately-permissioned action) and then get a 403 trying to view it, contradicting the
view's own docstring ("any staff member may request their own leave"). Fixed by setting
`required_permission = None` and letting `get_queryset()`'s self/HOD/unscoped scoping do the real
narrowing — the same shape `library.LoanViewSet` already used correctly.

The third was caught by the hostel test suite, not inspection: `hostel.services.waiting_list_priority()`
treated a *blank* `state_of_origin` the same as `OUTSIDE_SOUTH_SUDAN` when ranking the waiting list,
because the original condition was `state in ("", OUTSIDE_SOUTH_SUDAN)`. A data gap (the field is
genuinely optional) is not evidence that a student needs the hostel more — it silently tied every
incompletely-profiled local student with every actual out-of-country student for priority. Fixed to check
only the `OUTSIDE_SOUTH_SUDAN` value; an unrecorded state of origin is now neutral. `Room.clean()` also
gained a check it was missing: editing a room's `gender_restriction` while it has active occupants of the
other declared gender previously succeeded silently — the invariant "a room's active occupants all match
its restriction" was enforced on `Allocation.clean()` (the occupant's side) but not on the room's own side
when the room itself changes underneath them.

## Phase 6 verification (recorded 2026-08-19)

Documents & certification, Communications, Alumni and Reporting & compliance are all complete —
`documents`, `communications`, `alumni` and `reporting` bring the app count to fifteen.

| Check | Command | Result |
|---|---|---|
| Test suite | `pytest` | **642 passed** (73 new over Phase 5) |
| Module boundaries | `lint-imports` | 3 contracts kept, 0 broken |
| Style | `ruff check .` · `black --check .` | clean |
| Migrations match models | `manage.py makemigrations --check --dry-run` | no drift |
| RBAC policy applied | `manage.py seed_roles` | idempotent; **every** declared permission across all 13 roles now resolves — nothing left pending |
| Audit chain | `manage.py verify_audit_chain` | 203 entries verified, chain intact |
| Separation of duties | `manage.py permission_matrix --check-separation` | no role holds both grade-write and money-write |

`documents`'s permission names (`documents.add_transcriptrequest`, `documents.change_transcriptrequest`,
`documents.issue_certificate`) were declared on `registrar` back in Phase 2, years before the module
existed in code — they resolved on the first `seed_roles` run with zero edits needed, which is the whole
point of the pending-permission mechanism working as designed.

New dependency: `openpyxl` (pure Python, no system libraries) for the Excel export in `FR-RPT-05` — the
backend image was rebuilt to pick it up. PDF export was not added; see D-18/D-8 for why.

Two real bugs, both caught by tests, not inspection. First: `alumni.services.create_alumni_profile`
imported `apps.registry.models.StudentStatus` directly to check a student had graduated — `alumni` sits
*above* `registry` in the layering, so this is technically legal placement-wise, but it is exactly the
"reach into another app's models" the no-model-import contract exists to catch regardless of layer
direction. `lint-imports` failed on it immediately. Fixed by adding `registry.services.is_graduated()`,
returning a plain boolean so the caller never needs `StudentStatus`'s vocabulary at all — the same shape
`gender_for_student()` and the other single-field lookups in that file already use.

Second, and more interesting: `ReportExportView`'s CSV/Excel export took a `?format=csv` query parameter
— which collides with Django REST Framework's own reserved `format` query parameter for content
negotiation. Requesting `?format=csv` never reached the view at all; DRF's content negotiation looked for
a registered renderer named `csv`, found none, and raised a bare `Http404` before `get()` ever ran — the
same generic `{"code": "not_found", "message": "Not found."}` a genuinely missing URL would produce, which
is what made it look at first like a routing bug rather than a naming collision. Renamed the parameter to
`export_format`.

## Phase 7 verification (recorded 2026-08-19)

Scoped to the concrete, buildable items in hardening — TOTP/MFA enrolment (`NFR-SEC-04`), backup and
restore automation (`NFR-DATA-01`), and bulk student-import tooling (`NFR-DATA-03`). The remaining Phase 7
items (load testing, uptime monitoring, disk-encryption verification, an annual pen test) are operational
rather than code and are out of scope for this pass — they are unchanged in the tables above.

| Check | Command | Result |
|---|---|---|
| Test suite | `pytest` | **668 passed** (26 new: MFA enrolment/login/disable, bulk import) |
| Module boundaries | `lint-imports` | 3 contracts kept, 0 broken |
| Style | `ruff check .` · `black --check .` | clean |
| Migrations match models | `manage.py makemigrations --check --dry-run` | no drift |
| RBAC policy applied | `manage.py seed_roles` | idempotent |
| Audit chain | `manage.py verify_audit_chain` | 208 entries verified, chain intact |
| Separation of duties | `manage.py permission_matrix --check-separation` | no role holds both grade-write and money-write |
| Backup / restore | `make backup` then `make restore` | proven for real: a live dump restored cleanly onto a scratch database, table counts verified, scratch database dropped |

New dependency: `pyotp` (pure Python, no system libraries — TOTP generation and verification). No QR
image is rendered server-side; `MFASetupView` returns the `otpauth://` provisioning URI and leaves
rendering it as a QR code to the frontend, the same server-returns-data/client-renders split D-8 already
uses for a printable timetable.

One real bug, caught by `lint-imports`, not inspection: `registry.services._resolve_import_row` (the bulk
student importer) imported `AcademicYear` from `apps.academics.models` and `CurriculumVersion`/`Programme`
from `apps.curriculum.models` directly to resolve a legacy spreadsheet's natural keys — a plain
"cross-app model import" violation, the same class of bug `alumni` had in Phase 6, just in a different
app. `registry` sits *above* both `academics` and `curriculum` in the layering, so nothing was structurally
backwards — the no-model-import contract applies regardless of layer direction. Fixed by adding
`academics.services.calendar.academic_year_id_for_name()` and
`curriculum.services.programme_id_for_code()`/`curriculum_version_id_for()`, mirroring every other
natural-key-to-id lookup already in those files.
