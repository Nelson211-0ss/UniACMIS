"use client";

/** My results & grade appeals (FR-STU-02/06, FR-EXM-04…07) — published,
 * per-course results and cumulative GPA for the current semester, and a
 * form to appeal one. A result stays hidden until Senate approves it and
 * the examinations office publishes it, and is shown as withheld (never as
 * the marks themselves) while an outstanding hold blocks it — both
 * decisions the server makes; this page only reflects them. */

import { useEffect, useState } from "react";

import { AlertCircleIcon, CheckCircleIcon, LayersIcon } from "@/components/icons";
import { ApiFailure, api } from "@/lib/api";

interface CourseResult {
  registration_id: number;
  components: Array<{ assessment: string; weight_percent: string; score: string | null }>;
  complete: boolean;
  has_irregularity: boolean;
  configuration_error: string | null;
  percent: string | null;
  letter: string | null;
  grade_point: string | null;
  is_pass: boolean | null;
}

interface Appeal {
  id: number;
  registration: number;
  reason: string;
  status: string;
  decision_notes: string;
  created_at: string;
}

export default function ResultsPage() {
  const [semesterName, setSemesterName] = useState<string | null>(null);
  const [published, setPublished] = useState(false);
  const [withheld, setWithheld] = useState(false);
  const [holds, setHolds] = useState<Array<{ code: string; message: string }>>([]);
  const [courses, setCourses] = useState<CourseResult[]>([]);
  const [courseNames, setCourseNames] = useState<Map<number, { code: string; title: string }>>(
    new Map(),
  );
  const [gpa, setGpa] = useState<string | null>(null);
  const [appeals, setAppeals] = useState<Appeal[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [appealFor, setAppealFor] = useState<number | null>(null);
  const [appealReason, setAppealReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  async function load() {
    try {
      const [me, calendar, myAppeals] = await Promise.all([
        api.myStudent(),
        api.calendar(),
        api.myAppeals().catch(() => ({ results: [] as Appeal[] })),
      ]);
      setAppeals(myAppeals.results);
      if (!me || !calendar.semester) {
        setState("ready");
        return;
      }
      setSemesterName(calendar.semester.name);
      const [result, registrations] = await Promise.all([
        api.studentResult(me.id, calendar.semester.id),
        // The result payload only carries a bare registration id — this
        // semester's registrations (which do carry the course's name)
        // fill that in below rather than showing "Registration #7".
        api.myRegistrations(calendar.semester.id).catch(() => ({ results: [] })),
      ]);
      setPublished(result.published);
      setWithheld(result.withheld);
      setHolds(result.holds ?? []);
      setCourses(result.courses);
      setCourseNames(
        new Map(
          registrations.results.map((r) => [r.id, { code: r.course_code, title: r.course_title }]),
        ),
      );
      setGpa(result.gpa);
      setState("ready");
    } catch {
      setState("error");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function submitAppeal(registrationId: number) {
    if (!appealReason.trim()) return;
    setSubmitting(true);
    setNotice(null);
    try {
      await api.submitAppeal(registrationId, appealReason.trim());
      setNotice({ kind: "success", text: "Appeal submitted." });
      setAppealFor(null);
      setAppealReason("");
      await load();
    } catch (error) {
      setNotice({
        kind: "error",
        text: error instanceof ApiFailure ? error.error.message : "Could not submit the appeal.",
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Results &amp; appeals</h1>
          <p className="page-subtitle">{semesterName ?? "Results"}</p>
        </div>
      </div>

      {notice ? (
        <div className={`alert alert--${notice.kind === "success" ? "success" : "error"}`}>
          {notice.kind === "success" ? <CheckCircleIcon size={18} /> : <AlertCircleIcon size={18} />}
          <span>{notice.text}</span>
        </div>
      ) : null}

      {state === "error" ? (
        <div className="alert alert--error">
          <AlertCircleIcon size={18} />
          <span>Could not load your results. Try again shortly.</span>
        </div>
      ) : null}

      {state === "ready" && !published ? (
        <div className="alert alert--info">
          <AlertCircleIcon size={18} />
          <span>Results for this semester have not been published yet.</span>
        </div>
      ) : null}

      {state === "ready" && published && withheld ? (
        <div className="alert alert--warning">
          <AlertCircleIcon size={18} />
          <span>
            Your result has been withheld: {holds.map((h) => h.message).join(" ") || "contact the registrar's office."}
          </span>
        </div>
      ) : null}

      {state === "ready" && published && !withheld ? (
        <>
          <div className="grid">
            <div className="card stat stat--accent-blue">
              <div className="stat__top">
                <span className="stat__label">Semester GPA</span>
                <span className="stat__icon">
                  <LayersIcon size={18} />
                </span>
              </div>
              <div className="stat__value">{gpa ?? "—"}</div>
            </div>
          </div>

          <div className="card">
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Course</th>
                    <th>Percent</th>
                    <th>Grade</th>
                    <th>Points</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {courses.map((course) => (
                    <tr key={course.registration_id}>
                      <td className="cell-primary">
                        {courseNames.get(course.registration_id)?.code ??
                          `Registration #${course.registration_id}`}
                        <div className="text-sm muted">
                          {courseNames.get(course.registration_id)?.title ?? ""}
                        </div>
                      </td>
                      <td>{course.percent ?? "—"}</td>
                      <td>
                        {course.letter ? (
                          <span className={`pill ${course.is_pass ? "pill--synced" : "pill--failed"}`}>
                            {course.letter}
                          </span>
                        ) : (
                          <span className="pill">
                            {course.configuration_error ? "Not configured" : "Incomplete"}
                          </span>
                        )}
                      </td>
                      <td>{course.grade_point ?? "—"}</td>
                      <td>
                        {appealFor === course.registration_id ? (
                          <div style={{ display: "flex", gap: 6 }}>
                            <input
                              value={appealReason}
                              onChange={(event) => setAppealReason(event.target.value)}
                              placeholder="Reason for the appeal"
                              style={{ minWidth: 200 }}
                            />
                            <button
                              type="button"
                              className="sm"
                              disabled={submitting}
                              onClick={() => void submitAppeal(course.registration_id)}
                            >
                              Submit
                            </button>
                            <button
                              type="button"
                              className="ghost sm"
                              onClick={() => setAppealFor(null)}
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <button
                            type="button"
                            className="secondary sm"
                            onClick={() => setAppealFor(course.registration_id)}
                          >
                            Appeal
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : null}

      <div className="section-title">
        <LayersIcon size={16} />
        My appeals
      </div>
      <div className="card">
        {appeals.length === 0 ? (
          <p className="muted text-sm" style={{ margin: 0 }}>
            No appeals submitted.
          </p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Registration</th>
                  <th>Reason</th>
                  <th>Status</th>
                  <th>Decision</th>
                </tr>
              </thead>
              <tbody>
                {appeals.map((appeal) => (
                  <tr key={appeal.id}>
                    <td>#{appeal.registration}</td>
                    <td className="text-sm">{appeal.reason}</td>
                    <td>
                      <span
                        className={`pill ${
                          appeal.status === "upheld"
                            ? "pill--synced"
                            : appeal.status === "rejected"
                              ? "pill--failed"
                              : "pill--pending"
                        }`}
                      >
                        {appeal.status.replace(/_/g, " ")}
                      </span>
                    </td>
                    <td className="text-sm muted">{appeal.decision_notes || "—"}</td>
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
