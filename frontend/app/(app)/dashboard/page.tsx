"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { BarChartCard } from "@/components/charts/BarChartCard";
import { DonutChartCard } from "@/components/charts/DonutChartCard";
import { Stamp } from "@/components/Stamp";
import { StatTile, StatTileSkeleton } from "@/components/StatTile";
import {
  CalendarIcon,
  CheckCircleIcon,
  InboxIcon,
  UsersIcon,
  WifiOffIcon,
} from "@/components/icons";
import { ApiFailure, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { CHART_STATUS } from "@/lib/chartColors";
import { visibleNav } from "@/lib/nav";
import * as outbox from "@/lib/outbox";

interface CalendarState {
  configured: boolean;
  registration_open: boolean;
  academic_year: { name: string } | null;
  semester: { name: string } | null;
}

interface RevenueData {
  net_billed: string;
  collected: string;
  outstanding: string;
}

interface EnrollmentData {
  total: number;
  by_programme: Record<string, number>;
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export default function DashboardPage() {
  const { user, can, hasRole } = useAuth();
  const [calendar, setCalendar] = useState<CalendarState | null>(null);
  const [calendarLoaded, setCalendarLoaded] = useState(false);
  const [studentCount, setStudentCount] = useState<number | null>(null);
  const [studentsLoaded, setStudentsLoaded] = useState(false);
  const [queued, setQueued] = useState(0);
  const [offline, setOffline] = useState(false);

  const [revenue, setRevenue] = useState<RevenueData | null>(null);
  const [enrollment, setEnrollment] = useState<EnrollmentData | null>(null);
  const [programmeNames, setProgrammeNames] = useState<Map<number, string>>(new Map());

  const canSeeStudents = user?.permissions.includes("registry.view_student") ?? false;
  const canSeeAnalytics = can("reporting.view_dashboard");

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

    if (canSeeAnalytics) {
      Promise.all([api.reportingDashboard(), api.programmes()])
        .then(([widgets, programmePage]) => {
          setProgrammeNames(new Map(programmePage.results.map((p) => [p.id, p.code])));
          const revenueWidget = widgets.find((w) => w.key === "revenue");
          const enrollmentWidget = widgets.find((w) => w.key === "enrollment");
          if (revenueWidget) setRevenue(revenueWidget.data as unknown as RevenueData);
          if (enrollmentWidget) setEnrollment(enrollmentWidget.data as unknown as EnrollmentData);
        })
        .catch(() => undefined);
    }

    return unsubscribe;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canSeeStudents, canSeeAnalytics]);

  const firstName = user?.full_name.split(" ")[0] ?? "";
  const links = visibleNav(can, hasRole).filter((item) => item.href !== "/dashboard" && item.href !== "/outbox");
  const sections = [...new Set(links.map((item) => item.section))];

  const enrollmentByProgramme = enrollment
    ? Object.entries(enrollment.by_programme).map(([id, count]) => ({
        programme: programmeNames.get(Number(id)) ?? `#${id}`,
        students: count,
      }))
    : [];

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

        {revenue ? (
          <StatTile
            label="Outstanding revenue"
            value={Number(revenue.outstanding).toLocaleString()}
            icon={<CalendarIcon size={18} />}
            accent="rose"
            foot={`Net billed ${Number(revenue.net_billed).toLocaleString()}`}
          />
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

      {canSeeAnalytics && (enrollment || revenue) ? (
        <>
          <div className="dashboard-section">
            <h2>Analytics</h2>
            <Link href="/reporting" className="dashboard-section__link">
              Full report →
            </Link>
          </div>
          <div className="grid--split">
            {enrollment ? (
              <BarChartCard
                title="Enrollment by programme"
                subtitle={`${enrollment.total} active students`}
                data={enrollmentByProgramme}
                xKey="programme"
                series={[{ key: "students", label: "Students" }]}
              />
            ) : null}
            {revenue ? (
              <DonutChartCard
                title="Revenue: collected vs outstanding"
                data={[
                  { key: "collected", label: "Collected", value: Number(revenue.collected), color: CHART_STATUS.good },
                  { key: "outstanding", label: "Outstanding", value: Number(revenue.outstanding), color: CHART_STATUS.bad },
                ]}
              />
            ) : null}
          </div>
        </>
      ) : null}

      <div className="dashboard-section">
        <h2>Explore</h2>
      </div>
      {sections.map((section) => (
        <div key={section} style={{ marginBottom: 8 }}>
          <div className="section-title">{section}</div>
          <div className="grid grid--compact">
            {links
              .filter((item) => item.section === section)
              .map((item) => {
                const Icon = item.icon;
                return (
                  <Link key={item.href} href={item.href} className="card card--interactive quick-link" style={{ margin: 0 }}>
                    <span className="quick-link__icon">
                      <Icon size={18} />
                    </span>
                    <span className="quick-link__body">
                      <span className="quick-link__title">{item.label}</span>
                      <span className="quick-link__desc">{item.description}</span>
                    </span>
                  </Link>
                );
              })}
          </div>
        </div>
      ))}

      <div className="card">
        <div className="card__header">
          <span className="card__icon">
            <CheckCircleIcon size={18} />
          </span>
          <h2>What&rsquo;s live</h2>
        </div>
        <ul style={{ margin: "4px 0 0", padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 10 }}>
          {[
            "Foundation — accounts, roles, the audit trail, curriculum and the student registry",
            "Admissions, enrollment, timetabling, attendance and examinations",
            "Finance, HR, library and hostel",
            "Documents & certification, communications, alumni and reporting & analytics",
          ].map((line) => (
            <li key={line} style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
              <CheckCircleIcon size={18} style={{ color: "var(--status-verified)", marginTop: 1, flexShrink: 0 }} />
              <span className="muted">{line}</span>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}
