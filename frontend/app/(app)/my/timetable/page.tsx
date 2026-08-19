"use client";

/** My timetable (FR-STU-03, FR-TT-03) — the published class and exam
 * schedule. Shows only what has been published; a draft entry is never
 * shown to a student, the same publish/draft boundary the registrar's own
 * timetabling screen enforces. */

import { useEffect, useState } from "react";

import { CalendarIcon } from "@/components/icons";
import { api } from "@/lib/api";

interface Entry {
  id: number;
  course_code: string;
  course_title: string;
  room_code: string;
  lecturer_name: string;
  day_of_week: number;
  day_of_week_display: string;
  start_time: string;
  end_time: string;
}

interface ExamEntry {
  id: number;
  course_code: string;
  course_title: string;
  room_code: string;
  invigilator_names: string[];
  exam_date: string;
  start_time: string;
  end_time: string;
}

export default function TimetablePage() {
  const [semesterName, setSemesterName] = useState<string | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [examEntries, setExamEntries] = useState<ExamEntry[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    let cancelled = false;
    api
      .calendar()
      .then(async (calendar) => {
        if (!calendar.semester) {
          if (!cancelled) setState("ready");
          return;
        }
        setSemesterName(calendar.semester.name);
        const [timetable, exams] = await Promise.all([
          api.weeklyTimetable(calendar.semester.id),
          api.examTimetable(calendar.semester.id),
        ]);
        if (cancelled) return;
        setEntries([...timetable.results].sort((a, b) => a.day_of_week - b.day_of_week));
        setExamEntries(exams.results);
        setState("ready");
      })
      .catch(() => !cancelled && setState("error"));
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <div className="page-header">
        <div>
          <h1>My timetable</h1>
          <p className="page-subtitle">{semesterName ?? "Timetable"}</p>
        </div>
      </div>

      {state === "error" ? (
        <div className="alert alert--error">
          <span>Could not load the timetable. Try again shortly.</span>
        </div>
      ) : null}

      <div className="section-title">
        <CalendarIcon size={16} />
        Weekly classes
      </div>
      <div className="card">
        {state === "loading" ? (
          <p className="muted">Loading…</p>
        ) : entries.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__icon">
              <CalendarIcon size={26} />
            </span>
            <span className="empty-state__title">Nothing published yet</span>
            <span className="text-sm">
              The registrar has not published a class timetable for this semester.
            </span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Day</th>
                  <th>Time</th>
                  <th>Course</th>
                  <th>Room</th>
                  <th>Lecturer</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr key={entry.id}>
                    <td className="cell-primary">{entry.day_of_week_display}</td>
                    <td style={{ fontFamily: "var(--mono)" }}>
                      {entry.start_time}–{entry.end_time}
                    </td>
                    <td>
                      {entry.course_code}
                      <div className="text-sm muted">{entry.course_title}</div>
                    </td>
                    <td>{entry.room_code || "—"}</td>
                    <td>{entry.lecturer_name || "TBA"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="section-title">
        <CalendarIcon size={16} />
        Exam schedule
      </div>
      <div className="card">
        {state === "loading" ? (
          <p className="muted">Loading…</p>
        ) : examEntries.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__icon">
              <CalendarIcon size={26} />
            </span>
            <span className="empty-state__title">No exam sittings published</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Time</th>
                  <th>Course</th>
                  <th>Room</th>
                  <th>Invigilator</th>
                </tr>
              </thead>
              <tbody>
                {examEntries.map((entry) => (
                  <tr key={entry.id}>
                    <td className="cell-primary">{entry.exam_date}</td>
                    <td style={{ fontFamily: "var(--mono)" }}>
                      {entry.start_time}–{entry.end_time}
                    </td>
                    <td>
                      {entry.course_code}
                      <div className="text-sm muted">{entry.course_title}</div>
                    </td>
                    <td>{entry.room_code || "—"}</td>
                    <td>{entry.invigilator_names.join(", ") || "TBA"}</td>
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
