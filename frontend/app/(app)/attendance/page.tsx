"use client";

/** Attendance registers (FR-ATT-01…02). A lecturer marks their own class's
 * session roster; the examinations office checks a student's exam
 * eligibility against the configured threshold and grants a waiver when an
 * absence was authorised. Two independent actors, two independent sections —
 * neither role holds both permissions. */

import { useEffect, useState } from "react";

import { CheckCircleIcon, ClockIcon } from "@/components/icons";
import { ApiFailure, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Semester {
  id: number;
  name: string;
  academic_year_name: string;
  is_current: boolean;
}

interface TimetableEntryOption {
  id: number;
  course: number;
  course_code: string;
  course_title: string;
  day_of_week_display: string;
  start_time: string;
  end_time: string;
}

interface RosterEntry {
  registration_id: number;
  student_id: string;
  full_name: string;
  is_repeat: boolean;
}

const STATUS_OPTIONS = ["present", "absent", "late", "excused"];

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

export default function AttendancePage() {
  const { can } = useAuth();
  const canMark = can("attendance.add_sessionrecord");
  const canWaive = can("attendance.override_block");

  const [semesters, setSemesters] = useState<Semester[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "offline" | "error">("loading");
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const page = await api.semesters();
        setSemesters(page.results);
        setState("ready");
      } catch (error) {
        setState(error instanceof ApiFailure && error.offline ? "offline" : "error");
      }
    }
    void load();
  }, []);

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Attendance registers</h1>
          <p className="page-subtitle">Mark a class session and manage exam-eligibility waivers</p>
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
          <span>Could not load semesters. Try again shortly.</span>
        </div>
      ) : null}

      {canMark ? <MarkAttendanceSection semesters={semesters} onNotice={setNotice} /> : null}
      {canWaive ? <WaiverSection semesters={semesters} onNotice={setNotice} /> : null}

      {!canMark && !canWaive ? (
        <div className="card">
          <div className="empty-state">
            <span className="empty-state__title">Nothing to do here yet</span>
            <p className="muted">Your role has no attendance actions.</p>
          </div>
        </div>
      ) : null}
    </>
  );
}

function MarkAttendanceSection({
  semesters,
  onNotice,
}: {
  semesters: Semester[];
  onNotice: (notice: { kind: "success" | "error"; text: string }) => void;
}) {
  const [semesterId, setSemesterId] = useState<number | "">("");
  const [entries, setEntries] = useState<TimetableEntryOption[]>([]);
  const [entryId, setEntryId] = useState<number | "">("");
  const [sessionDate, setSessionDate] = useState(todayIso());
  const [roster, setRoster] = useState<RosterEntry[]>([]);
  const [marks, setMarks] = useState<Record<number, { status: string; notes: string }>>({});
  const [busy, setBusy] = useState(false);
  const [rosterState, setRosterState] = useState<"idle" | "loading" | "ready" | "error">("idle");

  useEffect(() => {
    const current = semesters.find((s) => s.is_current);
    if (current) setSemesterId(current.id);
  }, [semesters]);

  useEffect(() => {
    if (!semesterId) return;
    api
      .timetableEntries(Number(semesterId))
      .then((page) => setEntries(page.results))
      .catch(() => setEntries([]));
    setEntryId("");
    setRoster([]);
  }, [semesterId]);

  async function loadRoster() {
    const entry = entries.find((e) => e.id === entryId);
    if (!entry || !semesterId) return;
    setRosterState("loading");
    try {
      const [classList, existing] = await Promise.all([
        api.classList(entry.course, Number(semesterId)),
        api.sessionRecords(Number(entryId), sessionDate),
      ]);
      setRoster(classList);
      const seed: Record<number, { status: string; notes: string }> = {};
      for (const row of classList) seed[row.registration_id] = { status: "present", notes: "" };
      for (const record of existing.results) {
        seed[record.registration] = { status: record.status, notes: record.notes };
      }
      setMarks(seed);
      setRosterState("ready");
    } catch (error) {
      setRosterState("error");
      onNotice({
        kind: "error",
        text: error instanceof ApiFailure ? error.error.message : "Could not load the class roster.",
      });
    }
  }

  async function saveAttendance() {
    if (!entryId) return;
    setBusy(true);
    try {
      await api.recordAttendance(
        Number(entryId),
        sessionDate,
        roster.map((row) => ({
          registration_id: row.registration_id,
          status: marks[row.registration_id]?.status ?? "present",
          notes: marks[row.registration_id]?.notes ?? "",
        })),
      );
      onNotice({ kind: "success", text: `Attendance saved for ${sessionDate}.` });
    } catch (error) {
      onNotice({
        kind: "error",
        text: error instanceof ApiFailure ? error.error.message : "Could not save attendance.",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="card">
        <div className="card__header">
          <span className="card__icon">
            <ClockIcon size={18} />
          </span>
          <h2>Mark a session</h2>
        </div>
        <div className="field-row">
          <div className="field">
            <label htmlFor="att-semester">Semester</label>
            <select
              id="att-semester"
              value={semesterId}
              onChange={(event) => setSemesterId(event.target.value ? Number(event.target.value) : "")}
            >
              <option value="">Select…</option>
              {semesters.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} · {s.academic_year_name}
                </option>
              ))}
            </select>
          </div>
          <div className="field" style={{ flex: 2 }}>
            <label htmlFor="att-entry">Class</label>
            <select id="att-entry" value={entryId} onChange={(event) => setEntryId(event.target.value ? Number(event.target.value) : "")}>
              <option value="">Select…</option>
              {entries.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.course_code} — {entry.course_title} · {entry.day_of_week_display} {entry.start_time}–{entry.end_time}
                </option>
              ))}
            </select>
          </div>
          <div className="field" style={{ width: 160 }}>
            <label htmlFor="att-date">Session date</label>
            <input id="att-date" type="date" value={sessionDate} onChange={(event) => setSessionDate(event.target.value)} />
          </div>
        </div>
        <button type="button" disabled={!entryId || rosterState === "loading"} onClick={() => void loadRoster()}>
          Load roster
        </button>
      </div>

      {rosterState === "ready" ? (
        <div className="card">
          <div className="card__header">
            <h2>Roster — {sessionDate}</h2>
          </div>
          {roster.length === 0 ? (
            <div className="empty-state">
              <span className="empty-state__title">No students registered for this course this semester</span>
            </div>
          ) : (
            <>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Student</th>
                      <th>Status</th>
                      <th>Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {roster.map((row) => (
                      <tr key={row.registration_id}>
                        <td className="cell-primary">
                          {row.full_name}
                          <div className="text-sm muted" style={{ fontFamily: "var(--mono)" }}>
                            {row.student_id}
                          </div>
                        </td>
                        <td>
                          <select
                            value={marks[row.registration_id]?.status ?? "present"}
                            onChange={(event) =>
                              setMarks((prev) => ({
                                ...prev,
                                [row.registration_id]: { ...prev[row.registration_id], status: event.target.value },
                              }))
                            }
                          >
                            {STATUS_OPTIONS.map((status) => (
                              <option key={status} value={status}>
                                {status}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td>
                          <input
                            value={marks[row.registration_id]?.notes ?? ""}
                            onChange={(event) =>
                              setMarks((prev) => ({
                                ...prev,
                                [row.registration_id]: { ...prev[row.registration_id], notes: event.target.value },
                              }))
                            }
                            placeholder="Optional"
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <button type="button" disabled={busy} onClick={() => void saveAttendance()}>
                Save attendance
              </button>
            </>
          )}
        </div>
      ) : null}
    </>
  );
}

function WaiverSection({
  semesters,
  onNotice,
}: {
  semesters: Semester[];
  onNotice: (notice: { kind: "success" | "error"; text: string }) => void;
}) {
  const [courses, setCourses] = useState<Array<{ id: number; code: string; title: string }>>([]);
  const [semesterId, setSemesterId] = useState<number | "">("");
  const [courseId, setCourseId] = useState<number | "">("");
  const [roster, setRoster] = useState<RosterEntry[]>([]);
  const [eligibility, setEligibility] = useState<
    Record<number, { percentage: string | null; threshold: string; eligible: boolean; waived: boolean }>
  >({});
  const [reason, setReason] = useState<Record<number, string>>({});
  const [busyId, setBusyId] = useState<number | null>(null);

  useEffect(() => {
    api.courses().then((page) => setCourses(page.results)).catch(() => setCourses([]));
    const current = semesters.find((s) => s.is_current);
    if (current) setSemesterId(current.id);
  }, [semesters]);

  async function loadRoster() {
    if (!courseId || !semesterId) return;
    try {
      const classList = await api.classList(Number(courseId), Number(semesterId));
      setRoster(classList);
      setEligibility({});
    } catch (error) {
      onNotice({
        kind: "error",
        text: error instanceof ApiFailure ? error.error.message : "Could not load the class roster.",
      });
    }
  }

  async function checkEligibility(registrationId: number) {
    try {
      const result = await api.examEligibility(registrationId);
      setEligibility((prev) => ({ ...prev, [registrationId]: result }));
    } catch (error) {
      onNotice({
        kind: "error",
        text: error instanceof ApiFailure ? error.error.message : "Could not check eligibility.",
      });
    }
  }

  async function waive(registrationId: number) {
    const text = reason[registrationId] ?? "";
    if (text.trim().length < 5) {
      onNotice({ kind: "error", text: "Give a reason of at least 5 characters before granting a waiver." });
      return;
    }
    setBusyId(registrationId);
    try {
      const result = await api.grantWaiver(registrationId, text);
      setEligibility((prev) => ({ ...prev, [registrationId]: result }));
      onNotice({ kind: "success", text: "Waiver granted." });
    } catch (error) {
      onNotice({
        kind: "error",
        text: error instanceof ApiFailure ? error.error.message : "Could not grant the waiver.",
      });
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      <div className="card">
        <div className="card__header">
          <span className="card__icon">
            <CheckCircleIcon size={18} />
          </span>
          <h2>Exam eligibility &amp; waivers</h2>
        </div>
        <div className="field-row">
          <div className="field">
            <label htmlFor="waiver-semester">Semester</label>
            <select
              id="waiver-semester"
              value={semesterId}
              onChange={(event) => setSemesterId(event.target.value ? Number(event.target.value) : "")}
            >
              <option value="">Select…</option>
              {semesters.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} · {s.academic_year_name}
                </option>
              ))}
            </select>
          </div>
          <div className="field" style={{ flex: 2 }}>
            <label htmlFor="waiver-course">Course</label>
            <select id="waiver-course" value={courseId} onChange={(event) => setCourseId(event.target.value ? Number(event.target.value) : "")}>
              <option value="">Select…</option>
              {courses.map((course) => (
                <option key={course.id} value={course.id}>
                  {course.code} — {course.title}
                </option>
              ))}
            </select>
          </div>
        </div>
        <button type="button" disabled={!courseId || !semesterId} onClick={() => void loadRoster()}>
          Load roster
        </button>
      </div>

      {roster.length > 0 ? (
        <div className="card">
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Student</th>
                  <th>Eligibility</th>
                  <th>Waiver reason</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {roster.map((row) => {
                  const elig = eligibility[row.registration_id];
                  return (
                    <tr key={row.registration_id}>
                      <td className="cell-primary">
                        {row.full_name}
                        <div className="text-sm muted" style={{ fontFamily: "var(--mono)" }}>
                          {row.student_id}
                        </div>
                      </td>
                      <td>
                        {elig ? (
                          <span className={`pill ${elig.eligible ? "pill--synced" : "pill--failed"}`}>
                            {elig.percentage ?? "—"}% {elig.waived ? "(waived)" : elig.eligible ? "" : "below threshold"}
                          </span>
                        ) : (
                          <button type="button" className="sm secondary" onClick={() => void checkEligibility(row.registration_id)}>
                            Check
                          </button>
                        )}
                      </td>
                      <td>
                        {elig && !elig.eligible && !elig.waived ? (
                          <input
                            value={reason[row.registration_id] ?? ""}
                            onChange={(event) => setReason((prev) => ({ ...prev, [row.registration_id]: event.target.value }))}
                            placeholder="Reason for waiver"
                            style={{ minWidth: 160 }}
                          />
                        ) : null}
                      </td>
                      <td>
                        {elig && !elig.eligible && !elig.waived ? (
                          <button
                            type="button"
                            className="sm"
                            disabled={busyId === row.registration_id}
                            onClick={() => void waive(row.registration_id)}
                          >
                            Grant waiver
                          </button>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </>
  );
}
