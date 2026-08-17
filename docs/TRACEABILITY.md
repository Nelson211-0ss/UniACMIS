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
| FR-ADM-01 | Online application with bio-data + document upload | 2 | 📋 | |
| FR-ADM-02 | Offline/paper application intake by staff | 2 | 📋 | Uses the Phase 1 sync engine |
| FR-ADM-03 | Configurable programme entry requirements + validation | 2 | 🧱 | `Programme.entry_requirements` JSON exists in Phase 1 |
| FR-ADM-04 | Application fee recorded + reconciled before completion | 2/4 | 📋 | Needs `PaymentProvider`; mock exists Phase 1 |
| FR-ADM-05 | Admissions committee review with configurable scoring | 2 | 📋 | |
| FR-ADM-06 | Merit lists with quota rules (state, gender, disability, sponsorship) | 2 | 🧱 | Phase 1 captures the disaggregation fields the quotas need |
| FR-ADM-07 | Offer/rejection letters via portal, email, SMS | 2/6 | 🧱 | `NotificationProvider` interface defined Phase 1 |
| FR-ADM-08 | Convert accepted application → student record, auto student ID | 2 | 🧱 | ID generator built and tested in Phase 1 |

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
| FR-ENR-02 | Prerequisite + credit-limit validation | 2 | 🧱 | `Prerequisite`, `Programme.max_credits_per_semester` in place |
| FR-ENR-03 | Registration holds (fees, discipline, missing documents), configurable | 2/4 | ✅ | Provider interface + fake finance provider + tests in Phase 1 |
| FR-ENR-04 | Auto-generated class lists | 2 | 📋 | |
| FR-ENR-05 | Repeat/carry-over unit tracking | 3 | 📋 | |

### 3.5 Timetabling

| ID | Requirement | Phase | Status | Notes |
|---|---|---|---|---|
| FR-TT-01 | Automated clash-free timetable generation | 3 | 📋 | Manual entry + clash detection first; auto-generation a stretch goal |
| FR-TT-02 | Manual override | 3 | 📋 | |
| FR-TT-03 | Publish to portal + printable PDF for notice boards | 3 | 📋 | Print path matters for students without smartphones |
| FR-TT-04 | Exam timetable with invigilator assignment | 3 | 📋 | |

### 3.6 Attendance

| ID | Requirement | Phase | Status | Notes |
|---|---|---|---|---|
| FR-ATT-01 | Offline attendance capture with later sync | 3 | 🧱 | Sync engine + outbox proven in Phase 1; handler registered Phase 3 |
| FR-ATT-02 | Threshold flagging + exam block with authorised override | 3 | 🧱 | `Institution.attendance_threshold_percent` configurable from Phase 1 |

### 3.7 Examinations & assessment

| ID | Requirement | Phase | Status | Notes |
|---|---|---|---|---|
| FR-EXM-01 | CA score entry with configurable weighting | 3 | 📋 | |
| FR-EXM-02 | Grade-entry deadline enforcement + late-submission logging | 3 | 📋 | |
| FR-EXM-03 | Moderation / second-marking workflow | 3 | 📋 | |
| FR-EXM-04 | Automatic GPA/CGPA per configured grading scale | **1**/3 | ✅ | `GradingScale`/`GradeBand` + tested pure `gpa()`/`cgpa()` in Phase 1 |
| FR-EXM-05 | Senate/exam board approval before release | 3 | 📋 | Hard gate on publication |
| FR-EXM-06 | Withhold results for arrears/discipline, configurable | 3/4 | 🧱 | Reuses the hold-provider registry |
| FR-EXM-07 | Grade appeal / remark workflow | 3 | 📋 | |
| FR-EXM-08 | Missing-mark and irregularity flagging | 3 | 📋 | |

### 3.8 Finance & fees

| ID | Requirement | Phase | Status | Notes |
|---|---|---|---|---|
| FR-FIN-01 | Fee structures by programme/year/residency | 4 | 📋 | |
| FR-FIN-02 | Automatic semester invoices from registration | 4 | 📋 | |
| FR-FIN-03 | Bank slip, mobile money, cash, cheque + reconciliation | 4 | 🧱 | `PaymentProvider` + mock in Phase 1 |
| FR-FIN-04 | Scholarship/bursary/government-sponsored accounts tracked distinctly | 4 | 🧱 | `Student.sponsorship_type`, `Sponsor` in Phase 1 |
| FR-FIN-05 | Installment/payment plans with balance tracking | 4 | 📋 | |
| FR-FIN-06 | Automatic receipt on confirmed payment | 4 | 🧱 | `IdSequence` will issue receipt numbers |
| FR-FIN-07 | Defaulter reports + outstanding balance dashboards | 4 | 📋 | |
| FR-FIN-08 | Refund workflow with approval controls | 4 | 📋 | |

### 3.9 Human resources

| ID | Requirement | Phase | Status | Notes |
|---|---|---|---|---|
| FR-HR-01 | Staff bio-data, contracts, qualifications | **1**/5 | 🧱 | `StaffProfile` core record Phase 1; contracts + CV repository Phase 5 |
| FR-HR-02 | Leave application with multi-level approval | 5 | 📋 | |
| FR-HR-03 | Appraisal + promotion history | 5 | 📋 | |
| FR-HR-04 | Payroll-ready export | 5 | 📋 | Export only — payroll computation is out of scope (SRS §1.2) |

### 3.10–3.11 Library · Hostel

| ID | Requirement | Phase | Status | Notes |
|---|---|---|---|---|
| FR-LIB-01 | Catalogue of physical + electronic resources | 5 | 📋 | |
| FR-LIB-02 | Circulation, due dates, automatic fines | 5 | 📋 | Fines use `MoneyField` |
| FR-LIB-03 | Offline circulation with sync to central catalogue | 5 | 🧱 | Reuses Phase 1 sync engine |
| FR-HOS-01 | Room inventory + capacity | 5 | 📋 | |
| FR-HOS-02 | Allocation by configurable priority rules | 5 | 📋 | |
| FR-HOS-03 | Hostel fees linked to finance | 5 | 📋 | |

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
| FR-COM-01 | SMS for critical events | 6 | 🧱 | `NotificationProvider` + console impl Phase 1 |
| FR-COM-02 | Email as secondary channel | 6 | 🧱 | Same interface |
| FR-COM-03 | Bulk announcements to audiences (all students, class, **campus**) | 6 | ⏸ | Campus-scoped audience blocked by the multi-campus deferral below |
| FR-ALM-01 | Alumni contact + employment/tracer data | 6 | 📋 | |
| FR-ALM-02 | Alumni communication + event records | 6 | 📋 | |

### 3.15 Reporting & compliance

| ID | Requirement | Phase | Status | Notes |
|---|---|---|---|---|
| FR-RPT-01 | Configurable dashboards (enrollment, pass rates, revenue, ratios) | 6 | 📋 | |
| FR-RPT-02 | MoHEST statutory report templates, configurable | 6 | 🧱 | `Institution.mohest_code` Phase 1; formats unconfirmed (open item) |
| FR-RPT-03 | Disaggregation by gender, disability, state of origin | **1**/6 | ✅ | Fields captured as constrained choices in Phase 1 — free text would make this unreportable |
| FR-RPT-04 | Tamper-evident audit trail for all grade + financial data | **1** | ✅ | Hash-chained append-only `AuditLog` + `verify_audit_chain` |
| FR-RPT-05 | Custom report building, export Excel/PDF/CSV | 6 | 📋 | |

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
| NFR-SEC-04 | Salted hashing; MFA available for finance + registrar | **1**/4 | 🧱 | Django hashers + `mfa_enabled` hook; TOTP enrolment Phase 4 |
| NFR-SEC-05 | Security review / pen test before launch, annually after | 7 | 📋 | |
| NFR-USE-01 | English primary; text externalised for translation | **1** | ✅ | `gettext` from the start — retrofitting i18n means touching every template |
| NFR-USE-02 | Responsive 5-inch → desktop | **1** | ✅ | Mobile-first PWA shell |
| NFR-USE-03 | Critical notifications by SMS | 6 | 🧱 | Provider interface Phase 1 |
| NFR-MAINT-01 | Modular components, independently updatable | **1** | ✅ | Modular monolith + import-linter contracts in CI |
| NFR-MAINT-02 | Standard Linux, no proprietary vendor lock-in | **1** | ✅ | Docker Compose, Postgres, MinIO |
| NFR-MAINT-03 | Config data-driven, not hard-coded | **1** | ✅ | Calendar, grading scale, ID template, thresholds are rows |
| NFR-DATA-01 | Automated daily backups + periodic off-site replication | 7 | 📋 | `pg_dump` cron documented Phase 1, automated Phase 7 |
| NFR-DATA-02 | Documented retention + archival policy | 7 | 📋 | |
| NFR-DATA-03 | Bulk migration tooling with validation + rollback | 2 | 📋 | Legacy student/staff onboarding |

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
