"use client";

/** My attendance (FR-STU-04, FR-ATT-02) — per-course standing against the
 * institution's attendance threshold, and whether a low percentage is
 * currently blocking exam eligibility. */

import { useEffect, useState } from "react";

import { AlertCircleIcon, ClockIcon } from "@/components/icons";
import { api } from "@/lib/api";

interface Row {
  registrationId: number;
  courseCode: string;
  courseTitle: string;
  sessionsRecorded: number;
  sessionsAttended: number;
  percentage: string | null;
  threshold: string;
  belowThreshold: boolean;
  waived: boolean;
  eligible: boolean;
}

export default function AttendancePage() {
  const [semesterName, setSemesterName] = useState<string | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const calendar = await api.calendar();
        if (!calendar.semester) {
          if (!cancelled) setState("ready");
          return;
        }
        setSemesterName(calendar.semester.name);
        const registrations = await api.myRegistrations(calendar.semester.id);
        const active = registrations.results.filter((r) => r.status === "registered");
        const rows = await Promise.all(
          active.map(async (registration) => {
            const eligibility = await api.examEligibility(registration.id);
            return {
              registrationId: registration.id,
              courseCode: registration.course_code,
              courseTitle: registration.course_title,
              sessionsRecorded: eligibility.sessions_recorded,
              sessionsAttended: eligibility.sessions_attended,
              percentage: eligibility.percentage,
              threshold: eligibility.threshold,
              belowThreshold: eligibility.below_threshold,
              waived: eligibility.waived,
              eligible: eligibility.eligible,
            };
          }),
        );
        if (!cancelled) {
          setRows(rows);
          setState("ready");
        }
      } catch {
        if (!cancelled) setState("error");
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <div className="page-header">
        <div>
          <h1>My attendance</h1>
          <p className="page-subtitle">{semesterName ?? "Attendance standing"}</p>
        </div>
      </div>

      {state === "error" ? (
        <div className="alert alert--error">
          <AlertCircleIcon size={18} />
          <span>Could not load your attendance record. Try again shortly.</span>
        </div>
      ) : null}

      <div className="card">
        {state === "loading" ? (
          <p className="muted">Loading…</p>
        ) : rows.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__icon">
              <ClockIcon size={26} />
            </span>
            <span className="empty-state__title">Nothing to show</span>
            <span className="text-sm">
              You have no active course registrations this semester.
            </span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Course</th>
                  <th>Sessions</th>
                  <th>Attendance</th>
                  <th>Threshold</th>
                  <th>Exam eligibility</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.registrationId}>
                    <td>
                      <span className="cell-primary">{row.courseCode}</span>
                      <div className="text-sm muted">{row.courseTitle}</div>
                    </td>
                    <td>
                      {row.sessionsAttended} / {row.sessionsRecorded}
                    </td>
                    <td>
                      {row.percentage !== null ? (
                        <span className={`pill ${row.belowThreshold ? "pill--failed" : "pill--synced"}`}>
                          {row.percentage}%
                        </span>
                      ) : (
                        <span className="pill">No sessions yet</span>
                      )}
                    </td>
                    <td className="text-sm muted">{row.threshold}%</td>
                    <td>
                      {row.eligible ? (
                        <span className="pill pill--synced">
                          Eligible{row.waived ? " (waived)" : ""}
                        </span>
                      ) : (
                        <span className="pill pill--failed">Blocked</span>
                      )}
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
