"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  AlertCircleIcon,
  SearchIcon,
  UploadIcon,
  UserPlusIcon,
  UsersIcon,
  WifiOffIcon,
  XIcon,
} from "@/components/icons";
import { ApiFailure, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Student {
  id: number;
  student_id: string;
  full_name: string;
  programme_code: string;
  current_level: number;
  status: string;
}

const STATUS_PILL: Record<string, string> = {
  active: "pill--synced",
  graduated: "pill--info",
  suspended: "pill--failed",
  expelled: "pill--failed",
  deferred: "pill--pending",
  withdrawn: "pill--pending",
};

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function SkeletonRows() {
  return (
    <>
      {[0, 1, 2, 3, 4].map((row) => (
        <tr key={row}>
          <td colSpan={5}>
            <span className="skeleton skeleton-row" style={{ width: `${70 - row * 8}%` }} />
          </td>
        </tr>
      ))}
    </>
  );
}

export default function StudentsPage() {
  const { can } = useAuth();
  const [students, setStudents] = useState<Student[]>([]);
  const [count, setCount] = useState(0);
  const [search, setSearch] = useState("");
  const [state, setState] = useState<"loading" | "ready" | "offline" | "error">(
    "loading",
  );

  useEffect(() => {
    const timer = setTimeout(() => {
      const query = search.trim() ? `?search=${encodeURIComponent(search.trim())}` : "";
      api
        .students(query)
        .then((page) => {
          setStudents(page.results);
          setCount(page.count);
          setState("ready");
        })
        .catch((error) => {
          setState(error instanceof ApiFailure && error.offline ? "offline" : "error");
        });
    }, 300); // debounce: every keystroke should not be a request on a 2G link

    return () => clearTimeout(timer);
  }, [search]);

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Students</h1>
          <p className="page-subtitle">
            {state === "ready" ? `${count} on the register` : "Register"}
          </p>
        </div>
        {can("registry.add_student") ? (
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <Link href="/students/import" className="button secondary">
              <UploadIcon size={18} />
              Bulk import
            </Link>
            <Link href="/students/new" className="button">
              <UserPlusIcon size={18} />
              Admit a student
            </Link>
          </div>
        ) : null}
      </div>

      {state === "offline" ? (
        <div className="alert alert--warning">
          <WifiOffIcon size={18} />
          <span>No connection. Only students loaded earlier on this device are shown.</span>
        </div>
      ) : null}
      {state === "error" ? (
        <div className="alert alert--error">
          <AlertCircleIcon size={18} />
          <span>Could not load the register. Try again shortly.</span>
        </div>
      ) : null}

      <div className="card">
        <div className="field field--icon" style={{ marginBottom: 0 }}>
          <label htmlFor="search">Search</label>
          <SearchIcon size={16} />
          <input
            id="search"
            type="search"
            placeholder="Name, student ID or national ID"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          {search ? (
            <button
              type="button"
              className="field__clear icon-btn"
              onClick={() => setSearch("")}
              aria-label="Clear search"
            >
              <XIcon size={16} />
            </button>
          ) : null}
        </div>
      </div>

      <div className="card">
        {state !== "loading" && students.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__icon">
              <UsersIcon size={26} />
            </span>
            <span className="empty-state__title">No students match</span>
            <span className="text-sm">Try a different name, student ID or national ID.</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Student</th>
                  <th>Student ID</th>
                  <th>Programme</th>
                  <th>Year</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {state === "loading" ? (
                  <SkeletonRows />
                ) : (
                  students.map((student) => (
                    <tr key={student.id}>
                      <td>
                        <div className="row-flex">
                          <span className="avatar avatar--sm">{initials(student.full_name)}</span>
                          <span className="cell-primary">{student.full_name}</span>
                        </div>
                      </td>
                      <td style={{ fontFamily: "var(--mono)" }}>{student.student_id}</td>
                      <td>{student.programme_code}</td>
                      <td>{student.current_level}</td>
                      <td>
                        <span className={`pill ${STATUS_PILL[student.status] ?? ""}`}>
                          {student.status}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
