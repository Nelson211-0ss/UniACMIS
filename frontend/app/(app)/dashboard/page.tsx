"use client";

import { useEffect, useState } from "react";

import { ApiFailure, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import * as outbox from "@/lib/outbox";

interface CalendarState {
  configured: boolean;
  registration_open: boolean;
  academic_year: { name: string } | null;
  semester: { name: string } | null;
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [calendar, setCalendar] = useState<CalendarState | null>(null);
  const [studentCount, setStudentCount] = useState<number | null>(null);
  const [queued, setQueued] = useState(0);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    void outbox.countPending().then(setQueued);
    const unsubscribe = outbox.subscribe(() => void outbox.countPending().then(setQueued));

    api
      .calendar()
      .then(setCalendar)
      .catch((error) => {
        if (error instanceof ApiFailure && error.offline) setOffline(true);
      });

    if (user?.permissions.includes("registry.view_student")) {
      api
        .students("?page_size=1")
        .then((page) => setStudentCount(page.count))
        .catch(() => setStudentCount(null));
    }

    return unsubscribe;
  }, [user]);

  return (
    <>
      <h1>Dashboard</h1>
      <p className="page-subtitle">
        Signed in as {user?.full_name} · {user?.roles.join(", ") || "no role assigned"}
      </p>

      {offline ? (
        <div className="alert alert--warning">
          Working offline. Figures below may be out of date, and new entries will be
          queued on this device until the connection returns.
        </div>
      ) : null}

      <div className="grid">
        <section className="card">
          <h2>Academic calendar</h2>
          {calendar?.configured ? (
            <>
              <p className="muted">
                {calendar.academic_year?.name} · {calendar.semester?.name}
              </p>
              <span
                className={`pill ${calendar.registration_open ? "pill--synced" : ""}`}
              >
                Registration {calendar.registration_open ? "open" : "closed"}
              </span>
            </>
          ) : (
            <p className="muted">
              {offline
                ? "Not available offline."
                : "No current academic year or semester is set. The registrar sets these before registration can open."}
            </p>
          )}
        </section>

        {studentCount !== null ? (
          <section className="card">
            <h2>Students</h2>
            <p className="muted">On the register</p>
            <div style={{ fontSize: "2rem", fontWeight: 700 }}>{studentCount}</div>
          </section>
        ) : null}

        <section className="card">
          <h2>Offline queue</h2>
          <p className="muted">Entries on this device not yet sent</p>
          <div style={{ fontSize: "2rem", fontWeight: 700 }}>{queued}</div>
          {queued > 0 ? (
            <p className="muted" style={{ marginTop: 8, marginBottom: 0 }}>
              These are stored on this device and will send automatically. Nothing is
              lost if you close the browser.
            </p>
          ) : null}
        </section>
      </div>

      <section className="card">
        <h2>What this build covers</h2>
        <p className="muted">
          Phase 1 is the foundation: accounts and roles, the audit trail, the
          curriculum hierarchy, the student registry, and the offline-sync
          mechanism that attendance and grade entry will use in Phase 3.
        </p>
        <p className="muted" style={{ marginBottom: 0 }}>
          Registrars do their day-to-day work in the Django admin for now; this
          interface exists to prove the offline path end to end.
        </p>
      </section>
    </>
  );
}
