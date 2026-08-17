"use client";

import { useEffect, useState } from "react";

import { ApiFailure, api } from "@/lib/api";

interface Student {
  id: number;
  student_id: string;
  full_name: string;
  programme_code: string;
  current_level: number;
  status: string;
}

export default function StudentsPage() {
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
      <h1>Students</h1>
      <p className="page-subtitle">
        {state === "ready" ? `${count} on the register` : "Register"}
      </p>

      {state === "offline" ? (
        <div className="alert alert--warning">
          No connection. Only students loaded earlier on this device are shown.
        </div>
      ) : null}

      <div className="card">
        <div className="field" style={{ marginBottom: 0 }}>
          <label htmlFor="search">Search</label>
          <input
            id="search"
            type="search"
            placeholder="Name, student ID or national ID"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
      </div>

      <div className="card">
        {state === "loading" ? (
          <p className="muted" style={{ marginBottom: 0 }}>
            Loading…
          </p>
        ) : students.length === 0 ? (
          <p className="muted" style={{ marginBottom: 0 }}>
            No students match.
          </p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Student ID</th>
                  <th>Name</th>
                  <th>Programme</th>
                  <th>Year</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {students.map((student) => (
                  <tr key={student.id}>
                    <td style={{ fontFamily: "var(--mono)" }}>{student.student_id}</td>
                    <td>{student.full_name}</td>
                    <td>{student.programme_code}</td>
                    <td>{student.current_level}</td>
                    <td>
                      <span
                        className={`pill ${
                          student.status === "active" ? "pill--synced" : ""
                        }`}
                      >
                        {student.status}
                      </span>
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
