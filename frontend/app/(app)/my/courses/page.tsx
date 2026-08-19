"use client";

/** Course registration (FR-STU-05, FR-ENR-01…03) — register or drop a course
 * for the current semester. The registration rules themselves (prerequisites,
 * credit limits, holds, the add/drop window) are enforced by the server; this
 * page only has to show whatever it says clearly. */

import { useEffect, useState } from "react";

import { AlertCircleIcon, CheckCircleIcon, UserPlusIcon, XIcon } from "@/components/icons";
import { ApiFailure, api } from "@/lib/api";

interface CurriculumCourseRow {
  id: number;
  course: number;
  course_code: string;
  course_title: string;
  credit_hours: number;
  year_of_study: number;
  semester_sequence: number;
  is_core: boolean;
}

interface Registration {
  id: number;
  course: number;
  course_code: string;
  course_title: string;
  credit_hours: number;
  status: string;
}

export default function CourseRegistrationPage() {
  const [studentId, setStudentId] = useState<number | null>(null);
  const [semester, setSemester] = useState<{ id: number; name: string; sequence: number } | null>(
    null,
  );
  const [registrationOpen, setRegistrationOpen] = useState(false);
  const [courses, setCourses] = useState<CurriculumCourseRow[]>([]);
  const [registrations, setRegistrations] = useState<Registration[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [busyCourse, setBusyCourse] = useState<number | null>(null);
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  async function load() {
    try {
      const [me, calendar] = await Promise.all([api.myStudent(), api.calendar()]);
      if (!me || !calendar.semester) {
        setState("ready");
        return;
      }
      setStudentId(me.id);
      setSemester(calendar.semester);
      setRegistrationOpen(calendar.registration_open);

      const [version, regs] = await Promise.all([
        me.curriculum_version ? api.curriculumVersion(me.curriculum_version) : null,
        api.myRegistrations(calendar.semester.id),
      ]);
      setCourses(
        version
          ? version.courses.filter(
              (c) =>
                c.year_of_study === me.current_level &&
                c.semester_sequence === calendar.semester!.sequence,
            )
          : [],
      );
      setRegistrations(regs.results);
      setState("ready");
    } catch {
      setState("error");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function register(courseId: number) {
    if (!studentId || !semester) return;
    setBusyCourse(courseId);
    setNotice(null);
    try {
      await api.registerCourse(studentId, courseId, semester.id);
      setNotice({ kind: "success", text: "Registered." });
      await load();
    } catch (error) {
      setNotice({
        kind: "error",
        text: error instanceof ApiFailure ? error.error.message : "Could not register.",
      });
    } finally {
      setBusyCourse(null);
    }
  }

  async function drop(registrationId: number, courseId: number) {
    const reason = window.prompt("Reason for dropping this course:");
    if (!reason || !reason.trim()) return;
    setBusyCourse(courseId);
    setNotice(null);
    try {
      await api.dropRegistration(registrationId, reason.trim());
      setNotice({ kind: "success", text: "Dropped." });
      await load();
    } catch (error) {
      setNotice({
        kind: "error",
        text: error instanceof ApiFailure ? error.error.message : "Could not drop the course.",
      });
    } finally {
      setBusyCourse(null);
    }
  }

  const registeredByCourse = new Map(
    registrations.filter((r) => r.status === "registered").map((r) => [r.course, r]),
  );
  const totalCredits = registrations
    .filter((r) => r.status === "registered")
    .reduce((sum, r) => sum + r.credit_hours, 0);

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Course registration</h1>
          <p className="page-subtitle">
            {semester ? `${semester.name} · ${totalCredits} credit hours registered` : "Register"}
          </p>
        </div>
      </div>

      {notice ? (
        <div className={`alert alert--${notice.kind === "success" ? "success" : "error"}`}>
          {notice.kind === "success" ? <CheckCircleIcon size={18} /> : <AlertCircleIcon size={18} />}
          <span>{notice.text}</span>
        </div>
      ) : null}

      {state === "ready" && !registrationOpen ? (
        <div className="alert alert--warning">
          <AlertCircleIcon size={18} />
          <span>Registration is closed for the current semester.</span>
        </div>
      ) : null}

      {state === "error" ? (
        <div className="alert alert--error">
          <AlertCircleIcon size={18} />
          <span>Could not load your registration. Try again shortly.</span>
        </div>
      ) : null}

      <div className="card">
        {state === "loading" ? (
          <p className="muted">Loading…</p>
        ) : courses.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__icon">
              <UserPlusIcon size={26} />
            </span>
            <span className="empty-state__title">No courses to show</span>
            <span className="text-sm">
              Your curriculum has no courses scheduled for this year and semester, or your
              programme has not been assigned a curriculum version yet.
            </span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Course</th>
                  <th>Credit hours</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {courses.map((row) => {
                  const registration = registeredByCourse.get(row.course);
                  const busy = busyCourse === row.course;
                  return (
                    <tr key={row.id}>
                      <td>
                        <span className="cell-primary">{row.course_code}</span>
                        <div className="text-sm muted">{row.course_title}</div>
                      </td>
                      <td>{row.credit_hours}</td>
                      <td>
                        <span className={`pill ${row.is_core ? "" : "pill--info"}`}>
                          {row.is_core ? "Core" : "Elective"}
                        </span>
                      </td>
                      <td>
                        {registration ? (
                          <span className="pill pill--synced">Registered</span>
                        ) : (
                          <span className="pill">Not registered</span>
                        )}
                      </td>
                      <td>
                        {registration ? (
                          <button
                            type="button"
                            className="danger sm"
                            disabled={busy || !registrationOpen}
                            onClick={() => void drop(registration.id, row.course)}
                          >
                            <XIcon size={14} />
                            Drop
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="sm"
                            disabled={busy || !registrationOpen}
                            onClick={() => void register(row.course)}
                          >
                            <UserPlusIcon size={14} />
                            Register
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
