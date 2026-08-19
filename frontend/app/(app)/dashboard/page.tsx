"use client";

import { useEffect, useState } from "react";

import { Stamp } from "@/components/Stamp";
import { StatTile, StatTileSkeleton } from "@/components/StatTile";
import {
  CalendarIcon,
  CheckCircleIcon,
  InboxIcon,
  LayersIcon,
  UsersIcon,
  WifiOffIcon,
} from "@/components/icons";
import { ApiFailure, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import * as outbox from "@/lib/outbox";

interface CalendarState {
  configured: boolean;
  registration_open: boolean;
  academic_year: { name: string } | null;
  semester: { name: string } | null;
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [calendar, setCalendar] = useState<CalendarState | null>(null);
  const [calendarLoaded, setCalendarLoaded] = useState(false);
  const [studentCount, setStudentCount] = useState<number | null>(null);
  const [studentsLoaded, setStudentsLoaded] = useState(false);
  const [queued, setQueued] = useState(0);
  const [offline, setOffline] = useState(false);

  const canSeeStudents = user?.permissions.includes("registry.view_student") ?? false;

  useEffect(() => {
    void outbox.countPending().then(setQueued);
    const unsubscribe = outbox.subscribe(() => void outbox.countPending().then(setQueued));

    api
      .calendar()
      .then(setCalendar)
      .catch((error) => {
        if (error instanceof ApiFailure && error.offline) setOffline(true);
      })
      .finally(() => setCalendarLoaded(true));

    if (canSeeStudents) {
      api
        .students("?page_size=1")
        .then((page) => setStudentCount(page.count))
        .catch(() => setStudentCount(null))
        .finally(() => setStudentsLoaded(true));
    }

    return unsubscribe;
  }, [canSeeStudents]);

  const firstName = user?.full_name.split(" ")[0] ?? "";

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Welcome back, {firstName}</h1>
          <p className="page-subtitle">
            {user?.roles.map((r) => r.replace(/_/g, " ")).join(", ") || "No role assigned"}{" "}
            &middot; University Academic Management Information System
          </p>
        </div>
        <span className="avatar" aria-hidden="true">
          {user ? initials(user.full_name) : "?"}
        </span>
      </div>

      {offline ? (
        <div className="alert alert--warning">
          <WifiOffIcon size={18} />
          <span>
            Working offline. Figures below may be out of date, and new entries will
            be queued on this device until the connection returns.
          </span>
        </div>
      ) : null}

      <div className="grid">
        {!calendarLoaded ? (
          <StatTileSkeleton />
        ) : calendar?.configured ? (
          <StatTile
            label="Current semester"
            value={calendar.semester?.name ?? "—"}
            icon={<CalendarIcon size={18} />}
            accent="teal"
            foot={
              <span className={`pill ${calendar.registration_open ? "pill--synced" : ""}`}>
                Registration {calendar.registration_open ? "open" : "closed"}
              </span>
            }
          />
        ) : (
          <div className="card stat stat--accent-teal">
            <div className="stat__top">
              <span className="stat__label">Academic calendar</span>
              <span className="stat__icon">
                <CalendarIcon size={18} />
              </span>
            </div>
            <p className="muted text-sm" style={{ marginTop: 8, marginBottom: 0 }}>
              {offline
                ? "Not available offline."
                : "No current academic year or semester is set yet."}
            </p>
          </div>
        )}

        {canSeeStudents ? (
          !studentsLoaded ? (
            <StatTileSkeleton />
          ) : (
            <StatTile
              label="Students on the register"
              value={studentCount ?? "—"}
              icon={<UsersIcon size={18} />}
              accent="blue"
            />
          )
        ) : null}

        <StatTile
          label="Offline queue on this device"
          value={queued}
          icon={<InboxIcon size={18} />}
          accent="amber"
          foot={
            queued > 0 ? "Stored on this device — will send automatically" : "Nothing waiting"
          }
        />
      </div>

      {calendarLoaded && calendar?.configured ? (
        <div className="card" style={{ display: "flex", alignItems: "center", gap: 24 }}>
          <Stamp
            status={calendar.registration_open ? "verified" : "hold"}
            label={calendar.registration_open ? "Open" : "Closed"}
            size="sm"
          />
          <div>
            <h2>Registration {calendar.registration_open ? "is open" : "is closed"}</h2>
            <p className="muted" style={{ margin: "4px 0 0" }}>
              {calendar.semester?.name ?? "The current semester"} ·{" "}
              {calendar.academic_year?.name ?? "current academic year"}.{" "}
              {calendar.registration_open
                ? "Students may register for courses."
                : "Course registration is closed for this window."}
            </p>
          </div>
        </div>
      ) : null}

      <div className="card">
        <div className="card__header">
          <span className="card__icon">
            <LayersIcon size={18} />
          </span>
          <h2>What&rsquo;s live</h2>
        </div>
        <ul style={{ margin: "4px 0 0", padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 10 }}>
          {[
            "Foundation — accounts, roles, the audit trail, curriculum and the student registry",
            "Admissions & enrollment — applications, merit lists, course registration",
            "Timetabling, attendance & examinations — schedules, offline attendance capture, results",
          ].map((line) => (
            <li key={line} style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
              <CheckCircleIcon size={18} style={{ color: "var(--status-verified)", marginTop: 1, flexShrink: 0 }} />
              <span className="muted">{line}</span>
            </li>
          ))}
        </ul>
        <p className="muted text-sm" style={{ marginTop: 14, marginBottom: 0 }}>
          Registrars and other back-office staff still do most day-to-day work in the
          Django admin; this portal covers the self-service and offline-first paths.
        </p>
      </div>
    </>
  );
}
