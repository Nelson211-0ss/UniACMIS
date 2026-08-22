"use client";

/** Examinations (FR-EXM-01…08). Five distinct actors touch a result before a
 * student ever sees it — a lecturer enters marks, the examinations office
 * flags irregularities, a HOD moderates, Senate approves, and examinations
 * publishes — and a grade appeal is decided by whichever of HOD/examinations
 * holds `decide_gradeappeal`. Every section below is gated on the specific
 * permission its action needs, never on the role name, so this page shows
 * exactly the same slice of the workflow the API would already allow. */

import { useEffect, useState } from "react";

import { AlertCircleIcon, CheckCircleIcon, LayersIcon } from "@/components/icons";
import { ApiFailure, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Semester {
  id: number;
  name: string;
  academic_year_name: string;
  is_current: boolean;
}
interface CourseOption {
  id: number;
  code: string;
  title: string;
}
interface Assessment {
  id: number;
  course: number;
  course_code: string;
  name: string;
  weight_percent: string;
  max_score: string;
  sequence: number;
  grade_entry_deadline: string | null;
}
interface Mark {
  id: number;
  registration: number;
  student_id: string;
  student_name: string;
  assessment: number;
  assessment_name: string;
  score: string;
  effective_score: string;
  is_late: boolean;
  moderated_score: string | null;
  moderation_notes: string;
  is_irregular: boolean;
  irregularity_notes: string;
}

function errorText(error: unknown, fallback: string) {
  return error instanceof ApiFailure ? error.error.message : fallback;
}

export default function ExaminationsPage() {
  const { can } = useAuth();
  const canViewAssessments = can("examinations.view_assessment");
  const canAddMark = can("examinations.add_mark");
  const canModerate = can("examinations.moderate_result");
  const canViewMark = can("examinations.view_mark");
  const canDecideAppeal = can("examinations.decide_gradeappeal");
  const canPublish = can("examinations.publish_result");
  const canApprove = can("examinations.approve_result");

  const [semesters, setSemesters] = useState<Semester[]>([]);
  const [courses, setCourses] = useState<CourseOption[]>([]);
  const [programmes, setProgrammes] = useState<Array<{ id: number; code: string; name: string }>>([]);
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "offline" | "error">("loading");

  useEffect(() => {
    async function load() {
      try {
        const [semesterPage, coursePage, programmePage] = await Promise.all([
          api.semesters(),
          api.courses(),
          canPublish ? api.programmes() : Promise.resolve({ results: [] as Array<{ id: number; code: string; name: string }> }),
        ]);
        setSemesters(semesterPage.results);
        setCourses(coursePage.results);
        setProgrammes(programmePage.results);
        setState("ready");
      } catch (error) {
        setState(error instanceof ApiFailure && error.offline ? "offline" : "error");
      }
    }
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const showAnything = canViewAssessments || canAddMark || canModerate || canViewMark || canDecideAppeal || canPublish || canApprove;

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Examinations</h1>
          <p className="page-subtitle">Mark entry, moderation, appeals and result approval</p>
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
          <span>Could not load courses and semesters. Try again shortly.</span>
        </div>
      ) : null}

      {canAddMark ? (
        <MarkEntrySection semesters={semesters} courses={courses} canFlag={can("examinations.flag_irregularity")} onNotice={setNotice} />
      ) : null}

      {canViewAssessments ? (
        <AssessmentsSection courses={courses} canAdd={can("examinations.add_assessment")} onNotice={setNotice} />
      ) : null}

      {canModerate ? <ModerationSection courses={courses} onNotice={setNotice} /> : null}

      {canViewMark && !canAddMark ? <MissingMarksSection semesters={semesters} courses={courses} onNotice={setNotice} /> : null}

      {canDecideAppeal ? <AppealsSection onNotice={setNotice} /> : null}

      {canPublish || canApprove ? (
        <ApprovalsSection
          semesters={semesters}
          programmes={programmes}
          canSubmit={canPublish}
          canPublishApproved={canPublish}
          canApprove={canApprove}
          onNotice={setNotice}
        />
      ) : null}

      {!showAnything ? (
        <div className="card">
          <div className="empty-state">
            <span className="empty-state__title">Nothing to do here yet</span>
            <p className="muted">Your role has no examinations actions.</p>
          </div>
        </div>
      ) : null}
    </>
  );
}

// ------------------------------------------------------------ mark entry

function MarkEntrySection({
  semesters,
  courses,
  canFlag,
  onNotice,
}: {
  semesters: Semester[];
  courses: CourseOption[];
  canFlag: boolean;
  onNotice: (n: { kind: "success" | "error"; text: string }) => void;
}) {
  const [semesterId, setSemesterId] = useState<number | "">("");
  const [courseId, setCourseId] = useState<number | "">("");
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [assessmentId, setAssessmentId] = useState<number | "">("");
  const [rows, setRows] = useState<
    Array<{ registration_id: number; student_id: string; full_name: string; markId: number | null; score: string; irregular: boolean }>
  >([]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [flagging, setFlagging] = useState<number | null>(null);
  const [flagNotes, setFlagNotes] = useState<Record<number, string>>({});

  useEffect(() => {
    const current = semesters.find((s) => s.is_current);
    if (current) setSemesterId(current.id);
  }, [semesters]);

  useEffect(() => {
    if (!courseId) {
      setAssessments([]);
      return;
    }
    api.assessments(Number(courseId)).then((page) => setAssessments(page.results)).catch(() => setAssessments([]));
    setAssessmentId("");
  }, [courseId]);

  async function loadRoster() {
    if (!courseId || !semesterId || !assessmentId) return;
    try {
      const [roster, marksPage] = await Promise.all([
        api.classList(Number(courseId), Number(semesterId)),
        api.marksForAssessment(Number(assessmentId)),
      ]);
      const byRegistration = new Map(marksPage.results.map((mark) => [mark.registration, mark]));
      setRows(
        roster.map((entry) => {
          const mark = byRegistration.get(entry.registration_id);
          return {
            registration_id: entry.registration_id,
            student_id: entry.student_id,
            full_name: entry.full_name,
            markId: mark?.id ?? null,
            score: mark?.score ?? "",
            irregular: mark?.is_irregular ?? false,
          };
        }),
      );
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not load the roster.") });
    }
  }

  async function saveScore(row: (typeof rows)[number]) {
    if (!assessmentId || row.score.trim() === "") return;
    setBusyId(row.registration_id);
    try {
      await api.recordMark(row.registration_id, Number(assessmentId), row.score);
      onNotice({ kind: "success", text: `Saved ${row.full_name}'s mark.` });
      await loadRoster();
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not save this mark.") });
    } finally {
      setBusyId(null);
    }
  }

  async function submitFlag(row: (typeof rows)[number], notes: string) {
    if (!row.markId || notes.trim().length < 5) {
      onNotice({ kind: "error", text: "Give a reason of at least 5 characters to flag an irregularity." });
      return;
    }
    try {
      await api.flagIrregularity(row.markId, notes);
      onNotice({ kind: "success", text: "Marked irregular." });
      setFlagging(null);
      await loadRoster();
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not flag this mark.") });
    }
  }

  async function clearFlag(row: (typeof rows)[number]) {
    if (!row.markId) return;
    try {
      await api.clearIrregularity(row.markId);
      onNotice({ kind: "success", text: "Irregularity cleared." });
      await loadRoster();
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not clear this flag.") });
    }
  }

  return (
    <>
      <div className="card">
        <div className="card__header">
          <span className="card__icon">
            <LayersIcon size={18} />
          </span>
          <h2>Enter marks</h2>
        </div>
        <div className="field-row">
          <div className="field">
            <label htmlFor="me-semester">Semester</label>
            <select id="me-semester" value={semesterId} onChange={(event) => setSemesterId(event.target.value ? Number(event.target.value) : "")}>
              <option value="">Select…</option>
              {semesters.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          <div className="field" style={{ flex: 2 }}>
            <label htmlFor="me-course">Course</label>
            <select id="me-course" value={courseId} onChange={(event) => setCourseId(event.target.value ? Number(event.target.value) : "")}>
              <option value="">Select…</option>
              {courses.map((course) => (
                <option key={course.id} value={course.id}>
                  {course.code} — {course.title}
                </option>
              ))}
            </select>
          </div>
          <div className="field" style={{ flex: 2 }}>
            <label htmlFor="me-assessment">Assessment</label>
            <select id="me-assessment" value={assessmentId} onChange={(event) => setAssessmentId(event.target.value ? Number(event.target.value) : "")}>
              <option value="">Select…</option>
              {assessments.map((assessment) => (
                <option key={assessment.id} value={assessment.id}>
                  {assessment.name} ({assessment.weight_percent}%, max {assessment.max_score})
                </option>
              ))}
            </select>
          </div>
        </div>
        <button type="button" disabled={!courseId || !semesterId || !assessmentId} onClick={() => void loadRoster()}>
          Load roster
        </button>
      </div>

      {rows.length > 0 ? (
        <div className="card">
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Student</th>
                  <th>Score</th>
                  <th />
                  {canFlag ? <th>Irregularity</th> : null}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.registration_id}>
                    <td className="cell-primary">
                      {row.full_name}
                      <div className="text-sm muted" style={{ fontFamily: "var(--mono)" }}>
                        {row.student_id}
                      </div>
                    </td>
                    <td>
                      <input
                        value={row.score}
                        onChange={(event) =>
                          setRows((prev) =>
                            prev.map((r) => (r.registration_id === row.registration_id ? { ...r, score: event.target.value } : r)),
                          )
                        }
                        style={{ width: 80 }}
                      />
                    </td>
                    <td>
                      <button type="button" className="sm secondary" disabled={busyId === row.registration_id} onClick={() => void saveScore(row)}>
                        Save
                      </button>
                    </td>
                    {canFlag ? (
                      <td>
                        {row.irregular ? (
                          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                            <span className="pill pill--failed">Irregular</span>
                            <button type="button" className="sm ghost" onClick={() => void clearFlag(row)}>
                              Clear
                            </button>
                          </div>
                        ) : flagging === row.registration_id ? (
                          <div style={{ display: "flex", gap: 6 }}>
                            <input
                              placeholder="Reason"
                              style={{ minWidth: 140 }}
                              value={flagNotes[row.registration_id] ?? ""}
                              onChange={(event) =>
                                setFlagNotes((prev) => ({ ...prev, [row.registration_id]: event.target.value }))
                              }
                            />
                            <button
                              type="button"
                              className="sm danger"
                              onClick={() => void submitFlag(row, flagNotes[row.registration_id] ?? "")}
                            >
                              Flag
                            </button>
                          </div>
                        ) : row.markId ? (
                          <button type="button" className="sm ghost" onClick={() => setFlagging(row.registration_id)}>
                            Flag irregular
                          </button>
                        ) : (
                          "—"
                        )}
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </>
  );
}

// ------------------------------------------------------------ assessments

function AssessmentsSection({
  courses,
  canAdd,
  onNotice,
}: {
  courses: CourseOption[];
  canAdd: boolean;
  onNotice: (n: { kind: "success" | "error"; text: string }) => void;
}) {
  const [courseId, setCourseId] = useState<number | "">("");
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [name, setName] = useState("");
  const [weight, setWeight] = useState("20");
  const [maxScore, setMaxScore] = useState("100");
  const [busy, setBusy] = useState(false);

  async function reload(id: number) {
    const page = await api.assessments(id);
    setAssessments(page.results);
  }

  useEffect(() => {
    if (courseId) void reload(Number(courseId)).catch(() => setAssessments([]));
    else setAssessments([]);
  }, [courseId]);

  const totalWeight = assessments.reduce((sum, a) => sum + Number(a.weight_percent), 0);

  async function addAssessment() {
    if (!courseId || !name.trim()) return;
    setBusy(true);
    try {
      await api.createAssessment({ course: Number(courseId), name, weight_percent: weight, max_score: maxScore });
      onNotice({ kind: "success", text: "Assessment added." });
      setName("");
      await reload(Number(courseId));
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not add the assessment.") });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="section-title">Assessment schemes</div>
      <div className="card">
        <div className="field">
          <label htmlFor="as-course">Course</label>
          <select id="as-course" value={courseId} onChange={(event) => setCourseId(event.target.value ? Number(event.target.value) : "")}>
            <option value="">Select…</option>
            {courses.map((course) => (
              <option key={course.id} value={course.id}>
                {course.code} — {course.title}
              </option>
            ))}
          </select>
        </div>

        {courseId ? (
          <>
            {assessments.length > 0 && totalWeight !== 100 ? (
              <div className="alert alert--warning">
                <AlertCircleIcon size={16} />
                <span>Weights sum to {totalWeight}%, not 100% — a result can't be computed for this course until they do.</span>
              </div>
            ) : null}
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Weight</th>
                    <th>Max score</th>
                    <th>Deadline</th>
                  </tr>
                </thead>
                <tbody>
                  {assessments.map((a) => (
                    <tr key={a.id}>
                      <td className="cell-primary">{a.name}</td>
                      <td>{a.weight_percent}%</td>
                      <td>{a.max_score}</td>
                      <td>{a.grade_entry_deadline ? new Date(a.grade_entry_deadline).toLocaleString() : "—"}</td>
                    </tr>
                  ))}
                  {assessments.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="muted">
                        No assessment scheme yet for this course.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>

            {canAdd ? (
              <div className="field-row" style={{ marginTop: 12 }}>
                <div className="field" style={{ flex: 1 }}>
                  <label htmlFor="as-name">Name</label>
                  <input id="as-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="CA1" />
                </div>
                <div className="field" style={{ width: 100 }}>
                  <label htmlFor="as-weight">Weight %</label>
                  <input id="as-weight" value={weight} onChange={(event) => setWeight(event.target.value)} />
                </div>
                <div className="field" style={{ width: 100 }}>
                  <label htmlFor="as-max">Max score</label>
                  <input id="as-max" value={maxScore} onChange={(event) => setMaxScore(event.target.value)} />
                </div>
                <div style={{ alignSelf: "flex-end" }}>
                  <button type="button" disabled={busy} onClick={() => void addAssessment()}>
                    Add
                  </button>
                </div>
              </div>
            ) : null}
          </>
        ) : null}
      </div>
    </>
  );
}

// ------------------------------------------------------------ moderation

function ModerationSection({ courses, onNotice }: { courses: CourseOption[]; onNotice: (n: { kind: "success" | "error"; text: string }) => void }) {
  const [courseId, setCourseId] = useState<number | "">("");
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [assessmentId, setAssessmentId] = useState<number | "">("");
  const [marks, setMarks] = useState<Mark[]>([]);
  const [drafts, setDrafts] = useState<Record<number, { score: string; notes: string }>>({});
  const [busyId, setBusyId] = useState<number | null>(null);

  useEffect(() => {
    if (!courseId) {
      setAssessments([]);
      return;
    }
    api.assessments(Number(courseId)).then((page) => setAssessments(page.results)).catch(() => setAssessments([]));
    setAssessmentId("");
  }, [courseId]);

  async function loadMarks() {
    if (!assessmentId) return;
    try {
      const page = await api.marksForAssessment(Number(assessmentId));
      setMarks(page.results);
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not load marks for moderation.") });
    }
  }

  async function moderate(mark: Mark) {
    const draft = drafts[mark.id];
    if (!draft || draft.score.trim() === "" || draft.notes.trim().length < 5) {
      onNotice({ kind: "error", text: "Give a moderated score and a reason of at least 5 characters." });
      return;
    }
    setBusyId(mark.id);
    try {
      await api.moderateMark(mark.id, draft.score, draft.notes);
      onNotice({ kind: "success", text: `Moderated ${mark.student_name}'s mark.` });
      await loadMarks();
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not save this moderation.") });
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      <div className="section-title">Moderation</div>
      <div className="card">
        <div className="field-row">
          <div className="field" style={{ flex: 2 }}>
            <label htmlFor="mod-course">Course</label>
            <select id="mod-course" value={courseId} onChange={(event) => setCourseId(event.target.value ? Number(event.target.value) : "")}>
              <option value="">Select…</option>
              {courses.map((course) => (
                <option key={course.id} value={course.id}>
                  {course.code} — {course.title}
                </option>
              ))}
            </select>
          </div>
          <div className="field" style={{ flex: 2 }}>
            <label htmlFor="mod-assessment">Assessment</label>
            <select id="mod-assessment" value={assessmentId} onChange={(event) => setAssessmentId(event.target.value ? Number(event.target.value) : "")}>
              <option value="">Select…</option>
              {assessments.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </div>
        </div>
        <button type="button" disabled={!assessmentId} onClick={() => void loadMarks()}>
          Load marks
        </button>
      </div>

      {marks.length > 0 ? (
        <div className="card">
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Student</th>
                  <th>Original</th>
                  <th>Moderated</th>
                  <th>Notes</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {marks.map((mark) => (
                  <tr key={mark.id}>
                    <td className="cell-primary">
                      {mark.student_name}
                      {mark.is_irregular ? <span className="pill pill--failed" style={{ marginLeft: 6 }}>Irregular</span> : null}
                    </td>
                    <td>
                      {mark.score} {mark.moderated_score ? <span className="muted">→ {mark.moderated_score}</span> : null}
                    </td>
                    <td>
                      <input
                        style={{ width: 80 }}
                        value={drafts[mark.id]?.score ?? mark.moderated_score ?? ""}
                        onChange={(event) => setDrafts((prev) => ({ ...prev, [mark.id]: { ...prev[mark.id], score: event.target.value } }))}
                      />
                    </td>
                    <td>
                      <input
                        placeholder="Reason for moderation"
                        style={{ minWidth: 160 }}
                        value={drafts[mark.id]?.notes ?? ""}
                        onChange={(event) => setDrafts((prev) => ({ ...prev, [mark.id]: { ...prev[mark.id], notes: event.target.value } }))}
                      />
                    </td>
                    <td>
                      <button type="button" className="sm" disabled={busyId === mark.id} onClick={() => void moderate(mark)}>
                        Save
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </>
  );
}

// -------------------------------------------------------- missing marks

function MissingMarksSection({
  semesters,
  courses,
  onNotice,
}: {
  semesters: Semester[];
  courses: CourseOption[];
  onNotice: (n: { kind: "success" | "error"; text: string }) => void;
}) {
  const [semesterId, setSemesterId] = useState<number | "">("");
  const [courseId, setCourseId] = useState<number | "">("");
  const [missing, setMissing] = useState<Array<{ registration_id: number; assessment_id: number; assessment_name: string }> | null>(null);

  useEffect(() => {
    const current = semesters.find((s) => s.is_current);
    if (current) setSemesterId(current.id);
  }, [semesters]);

  async function load() {
    if (!courseId || !semesterId) return;
    try {
      const rows = await api.missingMarks(Number(courseId), Number(semesterId));
      setMissing(rows);
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not load the missing-marks report.") });
    }
  }

  return (
    <>
      <div className="section-title">Missing marks</div>
      <div className="card">
        <div className="field-row">
          <div className="field">
            <label htmlFor="mm-semester">Semester</label>
            <select id="mm-semester" value={semesterId} onChange={(event) => setSemesterId(event.target.value ? Number(event.target.value) : "")}>
              <option value="">Select…</option>
              {semesters.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          <div className="field" style={{ flex: 2 }}>
            <label htmlFor="mm-course">Course</label>
            <select id="mm-course" value={courseId} onChange={(event) => setCourseId(event.target.value ? Number(event.target.value) : "")}>
              <option value="">Select…</option>
              {courses.map((course) => (
                <option key={course.id} value={course.id}>
                  {course.code} — {course.title}
                </option>
              ))}
            </select>
          </div>
        </div>
        <button type="button" disabled={!courseId || !semesterId} onClick={() => void load()}>
          Check
        </button>

        {missing !== null ? (
          missing.length === 0 ? (
            <p className="muted" style={{ marginTop: 12 }}>
              Nothing missing — every registered student has a mark for every assessment.
            </p>
          ) : (
            <div className="table-scroll" style={{ marginTop: 12 }}>
              <table>
                <thead>
                  <tr>
                    <th>Registration</th>
                    <th>Assessment</th>
                  </tr>
                </thead>
                <tbody>
                  {missing.map((row) => (
                    <tr key={`${row.registration_id}-${row.assessment_id}`}>
                      <td>{row.registration_id}</td>
                      <td>{row.assessment_name}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        ) : null}
      </div>
    </>
  );
}

// ------------------------------------------------------------- appeals

function AppealsSection({ onNotice }: { onNotice: (n: { kind: "success" | "error"; text: string }) => void }) {
  const [appeals, setAppeals] = useState<
    Array<{ id: number; student_id: string; reason: string; status: string; decision_notes: string; created_at: string }>
  >([]);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [busyId, setBusyId] = useState<number | null>(null);
  const [loaded, setLoaded] = useState(false);

  async function reload() {
    try {
      const page = await api.gradeAppeals();
      setAppeals(page.results);
      setLoaded(true);
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not load grade appeals.") });
    }
  }

  useEffect(() => {
    void reload();
  }, []);

  async function decide(id: number, decision: "upheld" | "rejected") {
    const text = notes[id] ?? "";
    if (text.trim().length < 5) {
      onNotice({ kind: "error", text: "Give a reason of at least 5 characters before deciding." });
      return;
    }
    setBusyId(id);
    try {
      await api.decideAppeal(id, decision, text);
      onNotice({ kind: "success", text: `Appeal ${decision}.` });
      await reload();
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not decide this appeal.") });
    } finally {
      setBusyId(null);
    }
  }

  const pending = appeals.filter((a) => a.status === "submitted" || a.status === "under_review");
  const decided = appeals.filter((a) => !pending.includes(a));

  return (
    <>
      <div className="section-title">Grade appeals</div>
      <div className="card">
        {!loaded ? (
          <p className="muted">Loading…</p>
        ) : pending.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__title">No appeals awaiting a decision</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Student</th>
                  <th>Reason</th>
                  <th>Notes</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {pending.map((appeal) => (
                  <tr key={appeal.id}>
                    <td style={{ fontFamily: "var(--mono)" }}>{appeal.student_id}</td>
                    <td className="text-sm">{appeal.reason}</td>
                    <td>
                      <input
                        placeholder="Decision notes"
                        style={{ minWidth: 160 }}
                        value={notes[appeal.id] ?? ""}
                        onChange={(event) => setNotes((prev) => ({ ...prev, [appeal.id]: event.target.value }))}
                      />
                    </td>
                    <td style={{ display: "flex", gap: 6 }}>
                      <button type="button" className="sm" disabled={busyId === appeal.id} onClick={() => void decide(appeal.id, "upheld")}>
                        Uphold
                      </button>
                      <button type="button" className="sm danger" disabled={busyId === appeal.id} onClick={() => void decide(appeal.id, "rejected")}>
                        Reject
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {decided.length > 0 ? (
          <p className="text-sm muted" style={{ marginTop: 12 }}>
            {decided.length} appeal{decided.length === 1 ? "" : "s"} already decided.
          </p>
        ) : null}
      </div>
    </>
  );
}

// ---------------------------------------------------------- approvals

function ApprovalsSection({
  semesters,
  programmes,
  canSubmit,
  canPublishApproved,
  canApprove,
  onNotice,
}: {
  semesters: Semester[];
  programmes: Array<{ id: number; code: string; name: string }>;
  canSubmit: boolean;
  canPublishApproved: boolean;
  canApprove: boolean;
  onNotice: (n: { kind: "success" | "error"; text: string }) => void;
}) {
  const [approvals, setApprovals] = useState<
    Array<{ id: number; semester: number; programme: number | null; status: string; approval_notes: string }>
  >([]);
  const [semesterId, setSemesterId] = useState<number | "">("");
  const [programmeId, setProgrammeId] = useState<number | "">("");
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [busyId, setBusyId] = useState<number | null>(null);

  async function reload() {
    try {
      const page = await api.resultApprovals();
      setApprovals(page.results);
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not load result approvals.") });
    }
  }

  useEffect(() => {
    void reload();
  }, []);

  function semesterName(id: number) {
    return semesters.find((s) => s.id === id)?.name ?? `Semester #${id}`;
  }

  function programmeName(id: number | null) {
    if (id === null) return "All programmes";
    return programmes.find((p) => p.id === id)?.code ?? `Programme #${id}`;
  }

  async function submit() {
    if (!semesterId) return;
    try {
      await api.submitForApproval(Number(semesterId), programmeId || null);
      onNotice({ kind: "success", text: "Submitted for approval." });
      setProgrammeId("");
      await reload();
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not submit for approval.") });
    }
  }

  const PAST_TENSE: Record<"approve" | "reject" | "publish", string> = {
    approve: "approved",
    reject: "rejected",
    publish: "published",
  };

  async function act(id: number, action: "approve" | "reject" | "publish") {
    setBusyId(id);
    try {
      if (action === "approve") await api.approveResult(id, notes[id]);
      else if (action === "reject") await api.rejectResult(id, notes[id] ?? "");
      else await api.publishResult(id);
      onNotice({ kind: "success", text: `Result ${PAST_TENSE[action]}.` });
      await reload();
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, `Could not ${action} this result.`) });
    } finally {
      setBusyId(null);
    }
  }

  const STATUS_PILL: Record<string, string> = { pending: "pill--pending", approved: "pill--info", published: "pill--synced", rejected: "pill--failed" };

  return (
    <>
      <div className="section-title">Result approval &amp; publication</div>
      {canSubmit ? (
        <div className="card">
          <div className="card__header">
            <span className="card__icon">
              <CheckCircleIcon size={18} />
            </span>
            <h2>Submit a semester for approval</h2>
          </div>
          <div className="field-row">
            <div className="field" style={{ flex: 1 }}>
              <label htmlFor="ap-semester">Semester</label>
              <select id="ap-semester" value={semesterId} onChange={(event) => setSemesterId(event.target.value ? Number(event.target.value) : "")}>
                <option value="">Select…</option>
                {semesters.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label htmlFor="ap-programme">Programme</label>
              <select id="ap-programme" value={programmeId} onChange={(event) => setProgrammeId(event.target.value ? Number(event.target.value) : "")}>
                <option value="">All programmes</option>
                {programmes.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.code} — {p.name}
                  </option>
                ))}
              </select>
            </div>
            <div style={{ alignSelf: "flex-end" }}>
              <button type="button" disabled={!semesterId} onClick={() => void submit()}>
                Submit for approval
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <div className="card">
        {approvals.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__title">No approval requests yet</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Semester</th>
                  <th>Programme</th>
                  <th>Status</th>
                  <th>Notes</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {approvals.map((approval) => (
                  <tr key={approval.id}>
                    <td className="cell-primary">{semesterName(approval.semester)}</td>
                    <td>{programmeName(approval.programme)}</td>
                    <td>
                      <span className={`pill ${STATUS_PILL[approval.status] ?? ""}`}>{approval.status}</span>
                    </td>
                    <td>
                      {approval.status === "pending" && canApprove ? (
                        <input
                          placeholder="Notes"
                          style={{ minWidth: 140 }}
                          value={notes[approval.id] ?? ""}
                          onChange={(event) => setNotes((prev) => ({ ...prev, [approval.id]: event.target.value }))}
                        />
                      ) : (
                        approval.approval_notes || "—"
                      )}
                    </td>
                    <td style={{ display: "flex", gap: 6 }}>
                      {approval.status === "pending" && canApprove ? (
                        <>
                          <button type="button" className="sm" disabled={busyId === approval.id} onClick={() => void act(approval.id, "approve")}>
                            Approve
                          </button>
                          <button type="button" className="sm danger" disabled={busyId === approval.id} onClick={() => void act(approval.id, "reject")}>
                            Reject
                          </button>
                        </>
                      ) : null}
                      {approval.status === "approved" && canPublishApproved ? (
                        <button type="button" className="sm" disabled={busyId === approval.id} onClick={() => void act(approval.id, "publish")}>
                          Publish
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
