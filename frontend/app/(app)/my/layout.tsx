"use client";

/**
 * Shared shell for the student portal (`/my/*`) — one identity header
 * (photo, name, student ID, programme, year) instead of six pages each
 * deciding independently whether to show one, and one `api.myStudent()`
 * fetch instead of the three separate calls the pages used to make between
 * them. `useStudent()` (in `./student-context`) is how a page below reads
 * it back.
 */

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

import { StudentContext, type StudentIdentity } from "./student-context";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export default function StudentPortalLayout({ children }: { children: ReactNode }) {
  const { hasRole } = useAuth();
  const isStudent = hasRole("student");
  const [student, setStudent] = useState<StudentIdentity | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [photoFailed, setPhotoFailed] = useState(false);

  const load = useCallback(() => {
    if (!isStudent) {
      setLoaded(true);
      return;
    }
    api
      .myStudent()
      .then((result) => setStudent(result))
      .catch(() => undefined)
      .finally(() => setLoaded(true));
  }, [isStudent]);

  useEffect(() => {
    setPhotoFailed(false);
    load();
  }, [load]);

  return (
    <StudentContext.Provider value={{ student, loaded, reload: load }}>
      {!loaded ? (
        <div className="card" style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <span className="skeleton" style={{ width: 64, height: 64, borderRadius: "var(--radius-xs)" }} />
          <div style={{ display: "flex", flexDirection: "column", gap: 8, flex: 1 }}>
            <span className="skeleton skeleton-row" style={{ width: "40%" }} />
            <span className="skeleton skeleton-row" style={{ width: "60%" }} />
          </div>
        </div>
      ) : student ? (
        <div className="card" style={{ display: "flex", alignItems: "center", gap: 20, flexWrap: "wrap" }}>
          {student.photo && !photoFailed ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={student.photo}
              alt=""
              className="avatar avatar--lg avatar--square"
              onError={() => setPhotoFailed(true)}
            />
          ) : (
            <span className="avatar avatar--lg avatar--square" aria-hidden="true">
              {initials(student.full_name)}
            </span>
          )}
          <div style={{ minWidth: 0 }}>
            <h2>{student.full_name}</h2>
            <p className="muted" style={{ margin: "4px 0 0" }}>
              {student.student_id} &middot; {student.programme_name} &middot; Year {student.current_level}
            </p>
          </div>
        </div>
      ) : null}

      {children}
    </StudentContext.Provider>
  );
}
