"use client";

/**
 * Curriculum management (FR-CUR-01…03).
 *
 * Faculty → Department → Programme → Course, plus the versioned curriculum a
 * cohort is bound to. Two invariants the backend enforces and this page
 * surfaces rather than works around: exactly one curriculum version per
 * programme may be `active` at a time, and a prerequisite may not close a cycle
 * (which would make its own courses permanently unregisterable).
 */

import { useEffect, useState } from "react";

import { BookOpenIcon, BuildingIcon, LayersIcon } from "@/components/icons";
import { ApiFailure, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const AWARDS = ["certificate", "diploma", "bachelor", "postgraduate_diploma", "masters", "phd"];

interface Faculty {
  id: number;
  code: string;
  name: string;
  is_active: boolean;
}
interface Department {
  id: number;
  code: string;
  name: string;
  faculty: number;
  is_active: boolean;
}
interface Programme {
  id: number;
  code: string;
  name: string;
  award: string;
  department: number;
  department_name: string;
  duration_years: number;
  total_credits_required: number;
  is_active: boolean;
}
interface Course {
  id: number;
  code: string;
  title: string;
  credit_hours: number;
}
interface Version {
  id: number;
  programme: number;
  programme_code: string;
  version: string;
  status: string;
  effective_from: number;
  core_credits: number;
}

function errorText(error: unknown, fallback: string) {
  return error instanceof ApiFailure ? error.error.message : fallback;
}

export default function CurriculumPage() {
  const { can } = useAuth();
  const canManage = can("curriculum.add_programme");

  const [faculties, setFaculties] = useState<Faculty[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [programmes, setProgrammes] = useState<Programme[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [versions, setVersions] = useState<Version[]>([]);
  const [years, setYears] = useState<Array<{ id: number; name: string }>>([]);
  const [institutionId, setInstitutionId] = useState<number | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "offline" | "error">("loading");
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  async function load() {
    try {
      const [f, d, p, c, v, y, inst] = await Promise.all([
        api.faculties(),
        api.departments(),
        api.programmesDetailed(),
        api.courses(),
        api.curriculumVersions(),
        api.academicYears(),
        api.institution().catch(() => []),
      ]);
      setFaculties(f.results);
      setDepartments(d.results);
      setProgrammes(p.results);
      setCourses(c.results);
      setVersions(v.results);
      setYears(y.results);
      setInstitutionId(inst[0]?.id ?? null);
      setState("ready");
    } catch (error) {
      setState(error instanceof ApiFailure && error.offline ? "offline" : "error");
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Curriculum</h1>
          <p className="page-subtitle">Faculties, departments, programmes, courses and versions</p>
        </div>
      </div>

      {notice ? (
        <div className={`alert alert--${notice.kind === "success" ? "success" : "error"}`}>
          <span>{notice.text}</span>
        </div>
      ) : null}
      {state === "offline" ? (
        <div className="alert alert--warning">
          <span>No connection. Showing whatever loaded earlier on this device.</span>
        </div>
      ) : null}
      {state === "error" ? (
        <div className="alert alert--error">
          <span>Could not load the curriculum. Try again shortly.</span>
        </div>
      ) : null}

      <div className="grid">
        <div className="card stat stat--accent-blue">
          <div className="stat__top">
            <span className="stat__label">Programmes</span>
            <span className="stat__icon">
              <LayersIcon size={18} />
            </span>
          </div>
          <div className="stat__value">{programmes.length}</div>
        </div>
        <div className="card stat stat--accent-teal">
          <div className="stat__top">
            <span className="stat__label">Courses</span>
            <span className="stat__icon">
              <BookOpenIcon size={18} />
            </span>
          </div>
          <div className="stat__value">{courses.length}</div>
        </div>
        <div className="card stat stat--accent-amber">
          <div className="stat__top">
            <span className="stat__label">Departments</span>
            <span className="stat__icon">
              <BuildingIcon size={18} />
            </span>
          </div>
          <div className="stat__value">{departments.length}</div>
        </div>
      </div>

      {canManage ? (
        <HierarchyCard
          faculties={faculties}
          departments={departments}
          institutionId={institutionId}
          onNotice={setNotice}
          onChanged={() => void load()}
        />
      ) : null}

      {canManage ? (
        <ProgrammeCard
          departments={departments}
          programmes={programmes}
          onNotice={setNotice}
          onChanged={() => void load()}
        />
      ) : null}

      {canManage ? (
        <CourseCard departments={departments} courses={courses} onNotice={setNotice} onChanged={() => void load()} />
      ) : null}

      <VersionCard
        programmes={programmes}
        versions={versions}
        courses={courses}
        years={years}
        canManage={canManage}
        onNotice={setNotice}
        onChanged={() => void load()}
      />
    </>
  );
}

function HierarchyCard({
  faculties,
  departments,
  institutionId,
  onNotice,
  onChanged,
}: {
  faculties: Faculty[];
  departments: Department[];
  institutionId: number | null;
  onNotice: (n: { kind: "success" | "error"; text: string }) => void;
  onChanged: () => void;
}) {
  const [fCode, setFCode] = useState("");
  const [fName, setFName] = useState("");
  const [dFaculty, setDFaculty] = useState<number | "">("");
  const [dCode, setDCode] = useState("");
  const [dName, setDName] = useState("");
  const [busy, setBusy] = useState(false);

  async function addFaculty() {
    if (!fCode.trim() || !fName.trim() || institutionId === null) return;
    setBusy(true);
    try {
      await api.createFaculty({ institution: institutionId, code: fCode.trim(), name: fName.trim() });
      onNotice({ kind: "success", text: "Faculty added." });
      setFCode("");
      setFName("");
      onChanged();
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not add the faculty.") });
    } finally {
      setBusy(false);
    }
  }

  async function addDepartment() {
    if (!dFaculty || !dCode.trim() || !dName.trim()) return;
    setBusy(true);
    try {
      await api.createDepartment({ faculty: Number(dFaculty), code: dCode.trim(), name: dName.trim() });
      onNotice({ kind: "success", text: "Department added." });
      setDCode("");
      setDName("");
      onChanged();
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not add the department.") });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="section-title">Faculties &amp; departments</div>
      <div className="card">
        <div className="field-row">
          <div className="field" style={{ width: 110 }}>
            <label htmlFor="f-code">Faculty code</label>
            <input id="f-code" value={fCode} onChange={(event) => setFCode(event.target.value)} placeholder="ENG" />
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label htmlFor="f-name">Faculty name</label>
            <input id="f-name" value={fName} onChange={(event) => setFName(event.target.value)} />
          </div>
          <div style={{ alignSelf: "flex-end" }}>
            <button type="button" disabled={busy || institutionId === null} onClick={() => void addFaculty()}>
              Add faculty
            </button>
          </div>
        </div>

        <div className="field-row">
          <div className="field">
            <label htmlFor="d-faculty">Faculty</label>
            <select id="d-faculty" value={dFaculty} onChange={(event) => setDFaculty(event.target.value ? Number(event.target.value) : "")}>
              <option value="">Select…</option>
              {faculties.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.code} — {f.name}
                </option>
              ))}
            </select>
          </div>
          <div className="field" style={{ width: 110 }}>
            <label htmlFor="d-code">Dept code</label>
            <input id="d-code" value={dCode} onChange={(event) => setDCode(event.target.value)} placeholder="CSC" />
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label htmlFor="d-name">Department name</label>
            <input id="d-name" value={dName} onChange={(event) => setDName(event.target.value)} />
          </div>
          <div style={{ alignSelf: "flex-end" }}>
            <button type="button" className="secondary" disabled={busy} onClick={() => void addDepartment()}>
              Add department
            </button>
          </div>
        </div>

        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Faculty</th>
                <th>Departments</th>
              </tr>
            </thead>
            <tbody>
              {faculties.map((f) => (
                <tr key={f.id}>
                  <td className="cell-primary">
                    {f.code} — {f.name}
                  </td>
                  <td className="text-sm">
                    {departments.filter((d) => d.faculty === f.id).map((d) => d.code).join(", ") || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function ProgrammeCard({
  departments,
  programmes,
  onNotice,
  onChanged,
}: {
  departments: Department[];
  programmes: Programme[];
  onNotice: (n: { kind: "success" | "error"; text: string }) => void;
  onChanged: () => void;
}) {
  const [department, setDepartment] = useState<number | "">("");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [award, setAward] = useState("bachelor");
  const [duration, setDuration] = useState("4");
  const [credits, setCredits] = useState("120");
  const [busy, setBusy] = useState(false);

  async function add() {
    if (!department || !code.trim() || !name.trim()) return;
    setBusy(true);
    try {
      await api.createProgramme({
        department: Number(department),
        code: code.trim(),
        name: name.trim(),
        award,
        duration_years: Number(duration) || 4,
        total_credits_required: Number(credits) || 120,
      });
      onNotice({ kind: "success", text: "Programme added." });
      setCode("");
      setName("");
      onChanged();
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not add the programme.") });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="section-title">Programmes</div>
      <div className="card">
        <div className="field-row">
          <div className="field">
            <label htmlFor="p-department">Department</label>
            <select id="p-department" value={department} onChange={(event) => setDepartment(event.target.value ? Number(event.target.value) : "")}>
              <option value="">Select…</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.code} — {d.name}
                </option>
              ))}
            </select>
          </div>
          <div className="field" style={{ width: 110 }}>
            <label htmlFor="p-code">Code</label>
            <input id="p-code" value={code} onChange={(event) => setCode(event.target.value)} placeholder="BCS" />
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label htmlFor="p-name">Name</label>
            <input id="p-name" value={name} onChange={(event) => setName(event.target.value)} />
          </div>
        </div>
        <div className="field-row">
          <div className="field" style={{ width: 170 }}>
            <label htmlFor="p-award">Award</label>
            <select id="p-award" value={award} onChange={(event) => setAward(event.target.value)}>
              {AWARDS.map((a) => (
                <option key={a} value={a}>
                  {a.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </div>
          <div className="field" style={{ width: 110 }}>
            <label htmlFor="p-duration">Years</label>
            <input id="p-duration" value={duration} onChange={(event) => setDuration(event.target.value)} />
          </div>
          <div className="field" style={{ width: 130 }}>
            <label htmlFor="p-credits">Credits needed</label>
            <input id="p-credits" value={credits} onChange={(event) => setCredits(event.target.value)} />
          </div>
          <div style={{ alignSelf: "flex-end" }}>
            <button type="button" disabled={busy} onClick={() => void add()}>
              Add programme
            </button>
          </div>
        </div>

        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Code</th>
                <th>Name</th>
                <th>Award</th>
                <th>Years</th>
                <th>Credits</th>
              </tr>
            </thead>
            <tbody>
              {programmes.map((p) => (
                <tr key={p.id}>
                  <td className="cell-primary">{p.code}</td>
                  <td>{p.name}</td>
                  <td className="text-sm">{p.award.replace(/_/g, " ")}</td>
                  <td>{p.duration_years}</td>
                  <td>{p.total_credits_required}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function CourseCard({
  departments,
  courses,
  onNotice,
  onChanged,
}: {
  departments: Department[];
  courses: Course[];
  onNotice: (n: { kind: "success" | "error"; text: string }) => void;
  onChanged: () => void;
}) {
  const [department, setDepartment] = useState<number | "">("");
  const [code, setCode] = useState("");
  const [title, setTitle] = useState("");
  const [creditHours, setCreditHours] = useState("3");
  const [level, setLevel] = useState("1");
  const [busy, setBusy] = useState(false);

  const [prereqCourse, setPrereqCourse] = useState<number | "">("");
  const [prereqRequired, setPrereqRequired] = useState<number | "">("");
  const [prereqs, setPrereqs] = useState<Array<{ id: number; required_course_code: string }>>([]);

  async function add() {
    if (!department || !code.trim() || !title.trim()) return;
    setBusy(true);
    try {
      await api.createCourse({
        department: Number(department),
        code: code.trim(),
        title: title.trim(),
        credit_hours: Number(creditHours) || 3,
        level: Number(level) || 1,
      });
      onNotice({ kind: "success", text: "Course added." });
      setCode("");
      setTitle("");
      onChanged();
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not add the course.") });
    } finally {
      setBusy(false);
    }
  }

  async function loadPrereqs(courseId: number) {
    try {
      const page = await api.prerequisites(courseId);
      setPrereqs(page.results);
    } catch {
      setPrereqs([]);
    }
  }

  async function addPrereq() {
    if (!prereqCourse || !prereqRequired) return;
    setBusy(true);
    try {
      await api.addPrerequisite({ course: Number(prereqCourse), required_course: Number(prereqRequired) });
      onNotice({ kind: "success", text: "Prerequisite added." });
      setPrereqRequired("");
      await loadPrereqs(Number(prereqCourse));
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not add that prerequisite.") });
    } finally {
      setBusy(false);
    }
  }

  async function removePrereq(id: number) {
    try {
      await api.removePrerequisite(id);
      if (prereqCourse) await loadPrereqs(Number(prereqCourse));
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not remove that prerequisite.") });
    }
  }

  return (
    <>
      <div className="section-title">Courses</div>
      <div className="card">
        <div className="field-row">
          <div className="field">
            <label htmlFor="c-department">Department</label>
            <select id="c-department" value={department} onChange={(event) => setDepartment(event.target.value ? Number(event.target.value) : "")}>
              <option value="">Select…</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.code}
                </option>
              ))}
            </select>
          </div>
          <div className="field" style={{ width: 120 }}>
            <label htmlFor="c-code">Code</label>
            <input id="c-code" value={code} onChange={(event) => setCode(event.target.value)} placeholder="CSC101" />
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label htmlFor="c-title">Title</label>
            <input id="c-title" value={title} onChange={(event) => setTitle(event.target.value)} />
          </div>
          <div className="field" style={{ width: 90 }}>
            <label htmlFor="c-credits">Credits</label>
            <input id="c-credits" value={creditHours} onChange={(event) => setCreditHours(event.target.value)} />
          </div>
          <div className="field" style={{ width: 80 }}>
            <label htmlFor="c-level">Level</label>
            <input id="c-level" value={level} onChange={(event) => setLevel(event.target.value)} />
          </div>
          <div style={{ alignSelf: "flex-end" }}>
            <button type="button" disabled={busy} onClick={() => void add()}>
              Add course
            </button>
          </div>
        </div>
      </div>

      <div className="section-title">Prerequisites</div>
      <div className="card">
        <p className="text-sm muted" style={{ margin: "0 0 12px" }}>
          A chain that loops back on itself is rejected — it would make every course in the loop permanently
          unregisterable.
        </p>
        <div className="field-row">
          <div className="field" style={{ flex: 1 }}>
            <label htmlFor="pr-course">Course</label>
            <select
              id="pr-course"
              value={prereqCourse}
              onChange={(event) => {
                const value = event.target.value ? Number(event.target.value) : "";
                setPrereqCourse(value);
                if (value) void loadPrereqs(Number(value));
                else setPrereqs([]);
              }}
            >
              <option value="">Select…</option>
              {courses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.code} — {c.title}
                </option>
              ))}
            </select>
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label htmlFor="pr-required">Requires</label>
            <select id="pr-required" value={prereqRequired} onChange={(event) => setPrereqRequired(event.target.value ? Number(event.target.value) : "")}>
              <option value="">Select…</option>
              {courses
                .filter((c) => c.id !== prereqCourse)
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.code}
                  </option>
                ))}
            </select>
          </div>
          <div style={{ alignSelf: "flex-end" }}>
            <button type="button" disabled={busy || !prereqCourse || !prereqRequired} onClick={() => void addPrereq()}>
              Add prerequisite
            </button>
          </div>
        </div>

        {prereqCourse ? (
          prereqs.length === 0 ? (
            <p className="muted text-sm">No prerequisites recorded for this course.</p>
          ) : (
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {prereqs.map((pr) => (
                <span key={pr.id} className="pill pill--info" style={{ display: "inline-flex", gap: 4 }}>
                  {pr.required_course_code}
                  <button
                    type="button"
                    className="sm ghost"
                    style={{ padding: "0 4px", minHeight: 0 }}
                    onClick={() => void removePrereq(pr.id)}
                    aria-label={`Remove ${pr.required_course_code}`}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )
        ) : null}
      </div>
    </>
  );
}

function VersionCard({
  programmes,
  versions,
  courses,
  years,
  canManage,
  onNotice,
  onChanged,
}: {
  programmes: Programme[];
  versions: Version[];
  courses: Course[];
  years: Array<{ id: number; name: string }>;
  canManage: boolean;
  onNotice: (n: { kind: "success" | "error"; text: string }) => void;
  onChanged: () => void;
}) {
  const [programme, setProgramme] = useState<number | "">("");
  const [version, setVersion] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState<number | "">("");
  const [busy, setBusy] = useState(false);

  const [openVersion, setOpenVersion] = useState<number | null>(null);
  const [members, setMembers] = useState<
    Array<{ id: number; course_code: string; course_title: string; credit_hours: number; year_of_study: number; semester_sequence: number; is_core: boolean }>
  >([]);
  const [addCourse, setAddCourse] = useState<number | "">("");
  const [addYear, setAddYear] = useState("1");
  const [addSemester, setAddSemester] = useState("1");
  const [addCore, setAddCore] = useState(true);
  const [addGroup, setAddGroup] = useState("");

  useEffect(() => {
    const first = years[0];
    if (first) setEffectiveFrom(first.id);
  }, [years]);

  async function createVersion() {
    if (!programme || !version.trim() || !effectiveFrom) return;
    setBusy(true);
    try {
      await api.createCurriculumVersion({
        programme: Number(programme),
        version: version.trim(),
        effective_from: Number(effectiveFrom),
      });
      onNotice({ kind: "success", text: "Curriculum version created as a draft." });
      setVersion("");
      onChanged();
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not create that version.") });
    } finally {
      setBusy(false);
    }
  }

  async function openMembers(id: number) {
    if (openVersion === id) {
      setOpenVersion(null);
      setMembers([]);
      return;
    }
    try {
      const page = await api.curriculumCourses(id);
      setMembers(page.results);
      setOpenVersion(id);
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not load that version's courses.") });
    }
  }

  async function attach() {
    if (!openVersion || !addCourse) return;
    setBusy(true);
    try {
      await api.addCurriculumCourse({
        curriculum_version: openVersion,
        course: Number(addCourse),
        year_of_study: Number(addYear) || 1,
        semester_sequence: Number(addSemester) || 1,
        is_core: addCore,
        elective_group: addCore ? "" : addGroup.trim(),
      });
      onNotice({ kind: "success", text: "Course attached." });
      setAddCourse("");
      setAddGroup("");
      const page = await api.curriculumCourses(openVersion);
      setMembers(page.results);
      onChanged();
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not attach that course.") });
    } finally {
      setBusy(false);
    }
  }

  async function detach(id: number) {
    if (!openVersion) return;
    try {
      await api.removeCurriculumCourse(id);
      const page = await api.curriculumCourses(openVersion);
      setMembers(page.results);
      onChanged();
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not remove that course.") });
    }
  }

  return (
    <>
      <div className="section-title">Curriculum versions</div>
      <div className="card">
        <p className="text-sm muted" style={{ margin: "0 0 12px" }}>
          A cohort stays bound to the version it studied under. Only one version per programme may be active at a time.
        </p>

        {canManage ? (
          <div className="field-row">
            <div className="field" style={{ flex: 2 }}>
              <label htmlFor="v-programme">Programme</label>
              <select id="v-programme" value={programme} onChange={(event) => setProgramme(event.target.value ? Number(event.target.value) : "")}>
                <option value="">Select…</option>
                {programmes.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.code} — {p.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="field" style={{ width: 120 }}>
              <label htmlFor="v-version">Version</label>
              <input id="v-version" value={version} onChange={(event) => setVersion(event.target.value)} placeholder="2026" />
            </div>
            <div className="field">
              <label htmlFor="v-from">Effective from</label>
              <select id="v-from" value={effectiveFrom} onChange={(event) => setEffectiveFrom(event.target.value ? Number(event.target.value) : "")}>
                <option value="">Select…</option>
                {years.map((y) => (
                  <option key={y.id} value={y.id}>
                    {y.name}
                  </option>
                ))}
              </select>
            </div>
            <div style={{ alignSelf: "flex-end" }}>
              <button type="button" disabled={busy} onClick={() => void createVersion()}>
                Create
              </button>
            </div>
          </div>
        ) : null}

        {versions.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__title">No curriculum versions yet</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Programme</th>
                  <th>Version</th>
                  <th>Status</th>
                  <th>Core credits</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {versions.map((v) => (
                  <tr key={v.id}>
                    <td className="cell-primary">{v.programme_code}</td>
                    <td>{v.version}</td>
                    <td>
                      <span className={`pill ${v.status === "active" ? "pill--synced" : v.status === "retired" ? "pill--failed" : "pill--pending"}`}>
                        {v.status}
                      </span>
                    </td>
                    <td>{v.core_credits}</td>
                    <td>
                      <button type="button" className="sm secondary" onClick={() => void openMembers(v.id)}>
                        {openVersion === v.id ? "Close" : "Courses"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {openVersion ? (
        <div className="card">
          <div className="card__header">
            <h2>Courses in this version</h2>
          </div>
          {canManage ? (
            <div className="field-row">
              <div className="field" style={{ flex: 2 }}>
                <label htmlFor="cv-course">Course</label>
                <select id="cv-course" value={addCourse} onChange={(event) => setAddCourse(event.target.value ? Number(event.target.value) : "")}>
                  <option value="">Select…</option>
                  {courses
                    .filter((c) => !members.some((m) => m.course_code === c.code))
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.code} — {c.title}
                      </option>
                    ))}
                </select>
              </div>
              <div className="field" style={{ width: 90 }}>
                <label htmlFor="cv-year">Year</label>
                <input id="cv-year" value={addYear} onChange={(event) => setAddYear(event.target.value)} />
              </div>
              <div className="field" style={{ width: 100 }}>
                <label htmlFor="cv-sem">Semester</label>
                <input id="cv-sem" value={addSemester} onChange={(event) => setAddSemester(event.target.value)} />
              </div>
              <div className="field" style={{ width: 120 }}>
                <label htmlFor="cv-core">Type</label>
                <select id="cv-core" value={addCore ? "core" : "elective"} onChange={(event) => setAddCore(event.target.value === "core")}>
                  <option value="core">Core</option>
                  <option value="elective">Elective</option>
                </select>
              </div>
              {!addCore ? (
                <div className="field" style={{ width: 140 }}>
                  <label htmlFor="cv-group">Elective group</label>
                  <input id="cv-group" value={addGroup} onChange={(event) => setAddGroup(event.target.value)} placeholder="Required" />
                </div>
              ) : null}
              <div style={{ alignSelf: "flex-end" }}>
                <button type="button" disabled={busy || !addCourse} onClick={() => void attach()}>
                  Attach
                </button>
              </div>
            </div>
          ) : null}

          {members.length === 0 ? (
            <p className="muted">No courses attached yet.</p>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Course</th>
                    <th>Credits</th>
                    <th>Year</th>
                    <th>Semester</th>
                    <th>Type</th>
                    {canManage ? <th /> : null}
                  </tr>
                </thead>
                <tbody>
                  {members.map((m) => (
                    <tr key={m.id}>
                      <td className="cell-primary">
                        {m.course_code} — {m.course_title}
                      </td>
                      <td>{m.credit_hours}</td>
                      <td>{m.year_of_study}</td>
                      <td>{m.semester_sequence}</td>
                      <td>
                        <span className={`pill ${m.is_core ? "pill--info" : ""}`}>{m.is_core ? "Core" : "Elective"}</span>
                      </td>
                      {canManage ? (
                        <td>
                          <button type="button" className="sm ghost" onClick={() => void detach(m.id)}>
                            Remove
                          </button>
                        </td>
                      ) : null}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : null}
    </>
  );
}
