"use client";

/**
 * Head of Department dashboard.
 *
 * A HoD's queryset is department-scoped server-side (`ScopedQuerysetMixin`'s
 * `scope_to_department`), so every figure here is already about their own
 * department without this page filtering for it — with one exception noted
 * below, programmes, which have no per-department scoping on the viewset.
 *
 * The approval categories are the ones this system actually runs: grade appeals
 * a HoD decides, marks they moderate, and leave they endorse. Where a figure
 * needs data the university has not entered yet — a pass-rate trend before any
 * results are published — the panel says so rather than showing a zero that
 * looks like a finding.
 */

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { LineChartCard } from "@/components/charts/LineChartCard";
import {
  AlertCircleIcon,
  BookOpenIcon,
  BriefcaseIcon,
  CheckCircleIcon,
  ClockIcon,
  LayersIcon,
  MegaphoneIcon,
  UsersIcon,
} from "@/components/icons";
import { ApiFailure, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Appeal {
  id: number;
  student_id: string;
  reason: string;
  status: string;
  created_at: string;
}

interface Leave {
  id: number;
  staff_number: string;
  leave_type: string;
  start_date: string;
  end_date: string;
  status: string;
}

const ACTIONS = [
  {
    href: "/examinations",
    tile: "green" as const,
    icon: LayersIcon,
    title: "Grade Moderation",
    text: "Moderate marks and decide grade appeals for your department.",
    cta: "Review outcomes",
  },
  {
    href: "/attendance",
    tile: "blue" as const,
    icon: ClockIcon,
    title: "Attendance Registers",
    text: "Session attendance and exam eligibility across your courses.",
    cta: "View registers",
  },
  {
    href: "/hr",
    tile: "purple" as const,
    icon: BriefcaseIcon,
    title: "Leave & Appraisal",
    text: "Endorse staff leave requests and record annual appraisals.",
    cta: "Review requests",
  },
  {
    href: "/students",
    tile: "amber" as const,
    icon: UsersIcon,
    title: "Department Students",
    text: "The register for students on your department's programmes.",
    cta: "View students",
  },
  {
    href: "/communications",
    tile: "red" as const,
    icon: MegaphoneIcon,
    title: "Announcements",
    text: "Notices for your department's classes and staff.",
    cta: "View notices",
  },
];

export default function DepartmentDashboardPage() {
  const { user } = useAuth();

  const [departmentCode, setDepartmentCode] = useState<string | null>(null);
  const [programmes, setProgrammes] = useState(0);
  const [students, setStudents] = useState(0);
  const [staff, setStaff] = useState(0);
  const [courses, setCourses] = useState(0);
  const [classes, setClasses] = useState(0);
  const [registrations, setRegistrations] = useState(0);
  const [creditUnits, setCreditUnits] = useState(0);
  const [appeals, setAppeals] = useState<Appeal[]>([]);
  const [leave, setLeave] = useState<Leave[]>([]);
  const [notices, setNotices] = useState<Array<{ id: number; title: string; body: string; sent_at: string }>>([]);
  const [enrollmentTrend, setEnrollmentTrend] = useState<Array<{ label: string; students: number | null }>>([]);
  const [academicYear, setAcademicYear] = useState<string | null>(null);
  const [semesterName, setSemesterName] = useState<string | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "offline" | "error">("loading");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const calendar = await api.calendar();
        if (cancelled) return;
        setAcademicYear(calendar.academic_year?.name ?? null);
        setSemesterName(calendar.semester?.name ?? null);

        const [staffPage, studentPage, coursePage, programmePage, semesterPage] = await Promise.all([
          api.staffProfiles(),
          api.students("?page_size=1"),
          api.courses("?page_size=1"),
          api.programmesDetailed(),
          api.semesters(),
        ]);
        if (cancelled) return;

        setStudents(studentPage.count);
        setCourses(coursePage.results.length > 0 ? (coursePage as { count?: number }).count ?? 0 : 0);

        // The HoD's own staff row carries their department; the staff list is
        // department-scoped already, so this is for labelling and for filtering
        // programmes, which the viewset does not scope.
        const mine = staffPage.results.find((s) => s.full_name === user?.full_name);
        setDepartmentCode(mine?.department_code ?? null);
        setStaff(staffPage.results.length);
        setProgrammes(programmePage.results.length);

        if (calendar.semester) {
          const semesterId = calendar.semester.id;
          const [timetable, regs] = await Promise.all([
            api.timetableEntries(semesterId).catch(() => null),
            api.myRegistrations(semesterId).catch(() => null),
          ]);
          if (cancelled) return;
          if (timetable) setClasses(timetable.results.length);
          if (regs) {
            const active = regs.results.filter((r) => r.status === "registered");
            setRegistrations(active.length);
            setCreditUnits(active.reduce((sum, r) => sum + r.credit_hours, 0));
          }
        }

        // Registrations per semester, oldest first — a real trend where the
        // registry has history, and visibly empty where it does not.
        const trend = await Promise.all(
          semesterPage.results.map((semester) =>
            api
              .myRegistrations(semester.id)
              .then((page) => ({
                label: `${semester.academic_year_name.slice(2)}/${semester.sequence}`,
                students: page.results.filter((r) => r.status === "registered").length,
              }))
              .catch(() => ({ label: semester.name, students: null as number | null })),
          ),
        );
        if (!cancelled) setEnrollmentTrend(trend);

        const [appealPage, leavePage, noticePage] = await Promise.all([
          api.gradeAppeals("?page_size=10").catch(() => ({ results: [] as Appeal[] })),
          api.leaveRequests().catch(() => ({ results: [] as Leave[] })),
          api.announcements("?page_size=4").catch(() => ({ results: [] })),
        ]);
        if (cancelled) return;
        setAppeals(appealPage.results as Appeal[]);
        setLeave(leavePage.results as Leave[]);
        setNotices(noticePage.results);
        setState("ready");
      } catch (error) {
        if (!cancelled) setState(error instanceof ApiFailure && error.offline ? "offline" : "error");
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [user?.full_name]);

  const openAppeals = appeals.filter((a) => a.status === "submitted" || a.status === "under_review");
  const toEndorse = leave.filter((l) => l.status === "submitted");
  const pendingTotal = openAppeals.length + toEndorse.length;

  const firstName = user?.full_name ?? "";

  /** Approval requests across both queues, newest first. */
  const requests = useMemo(() => {
    const rows = [
      ...openAppeals.map((a) => ({
        key: `appeal-${a.id}`,
        type: "Grade appeal",
        detail: a.reason.length > 60 ? `${a.reason.slice(0, 60)}…` : a.reason,
        by: a.student_id,
        date: a.created_at,
        href: "/examinations",
      })),
      ...toEndorse.map((l) => ({
        key: `leave-${l.id}`,
        type: "Leave request",
        detail: `${l.leave_type} · ${l.start_date} → ${l.end_date}`,
        by: l.staff_number,
        date: l.start_date,
        href: "/hr",
      })),
    ];
    return rows.sort((a, b) => b.date.localeCompare(a.date)).slice(0, 6);
  }, [openAppeals, toEndorse]);

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Good day{firstName ? `, ${firstName}` : ""}</h1>
          <p className="page-subtitle">
            Head of Department dashboard
            {departmentCode ? ` · ${departmentCode}` : ""}
          </p>
        </div>
        <div style={{ display: "flex", gap: "var(--sp-3)", alignItems: "center", flexWrap: "wrap" }}>
          {academicYear ? (
            <span className="idchip">
              <span className="idchip__label">Academic year</span>
              <span className="idchip__value">{academicYear}</span>
            </span>
          ) : null}
          <Link href="/hr" className="button secondary">
            HR &amp; leave
          </Link>
        </div>
      </div>

      {state === "offline" ? (
        <div className="alert alert--warning">
          <span>No connection. Showing whatever loaded earlier on this device.</span>
        </div>
      ) : null}
      {state === "error" ? (
        <div className="alert alert--error">
          <span>Could not load the department dashboard. Try again shortly.</span>
        </div>
      ) : null}

      {/* ------------------------------------------------------- headline figures */}
      <div className="grid grid--stats">
        <div className="card figure">
          <span className="figure__tile figure__tile--green">
            <LayersIcon size={20} />
          </span>
          <span className="figure__label">Programmes</span>
          <span className="figure__value">{state === "loading" ? "…" : programmes}</span>
          <span className="figure__meta">Across the institution</span>
        </div>

        <div className="card figure">
          <span className="figure__tile figure__tile--blue">
            <UsersIcon size={20} />
          </span>
          <span className="figure__label">Students</span>
          <span className="figure__value">{state === "loading" ? "…" : students}</span>
          <span className="figure__meta">On your department&rsquo;s register</span>
          <Link href="/students" className="figure__link">
            View students →
          </Link>
        </div>

        <div className="card figure">
          <span className="figure__tile figure__tile--purple">
            <BriefcaseIcon size={20} />
          </span>
          <span className="figure__label">Teaching staff</span>
          <span className="figure__value">{state === "loading" ? "…" : staff}</span>
          <span className="figure__meta">In your department</span>
          <Link href="/hr" className="figure__link">
            View staff →
          </Link>
        </div>

        <div className="card figure">
          <span className="figure__tile figure__tile--amber">
            <BookOpenIcon size={20} />
          </span>
          <span className="figure__label">Courses</span>
          <span className="figure__value">{state === "loading" ? "…" : courses}</span>
          <span className="figure__meta">
            {classes > 0 ? `${classes} class${classes === 1 ? "" : "es"} timetabled` : "Catalogue entries"}
          </span>
        </div>

        <div className="card figure">
          <span className="figure__tile figure__tile--red">
            <AlertCircleIcon size={20} />
          </span>
          <span className="figure__label">Pending approvals</span>
          <span className={`figure__value ${pendingTotal > 0 ? "figure__value--red" : "figure__value--green"}`}>
            {state === "loading" ? "…" : pendingTotal}
          </span>
          <span className="figure__meta">{pendingTotal > 0 ? "Require your action" : "Nothing waiting"}</span>
        </div>
      </div>

      {/* ------------------------------ performance + approvals/quick stats */}
      <div className="grid--split" style={{ marginBottom: "var(--gap)" }}>
        {/* `LineChartCard` is itself a card — nesting it inside another one
            squeezes its ResponsiveContainer, so the note sits beside it as a
            sibling rather than sharing a wrapper. */}
        <div>
          <LineChartCard
            title="Department performance"
            subtitle={`Registrations by semester${semesterName ? ` · currently ${semesterName}` : ""}`}
            data={enrollmentTrend}
            xKey="label"
            series={[{ key: "students", label: "Registrations" }]}
            height={260}
          />
          <p className="text-sm muted" style={{ margin: "0 0 var(--gap)" }}>
            Pass-rate trends and per-programme performance appear here once results are published for a semester —
            they are computed from real marks rather than stored, so there is nothing to show until then.
          </p>
        </div>

        <div>
          <div className="card">
            <div className="panel__head">
              <h2>Pending approvals</h2>
              {pendingTotal > 0 ? <span className="attention__count">{pendingTotal}</span> : null}
            </div>
            <table className="detail">
              <tbody>
                <tr>
                  <th scope="row">Grade appeals</th>
                  <td className={openAppeals.length > 0 ? "is-red" : ""}>{openAppeals.length}</td>
                </tr>
                <tr>
                  <th scope="row">Leave to endorse</th>
                  <td className={toEndorse.length > 0 ? "is-red" : ""}>{toEndorse.length}</td>
                </tr>
                <tr>
                  <th scope="row">Marks to moderate</th>
                  <td>
                    <Link href="/examinations" className="panel__link">
                      Review →
                    </Link>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div className="card">
            <div className="panel__head">
              <h2>Quick stats</h2>
            </div>
            <table className="detail">
              <tbody>
                <tr>
                  <th scope="row">Courses offered</th>
                  <td>{courses}</td>
                </tr>
                <tr>
                  <th scope="row">Classes timetabled</th>
                  <td>{classes}</td>
                </tr>
                <tr>
                  <th scope="row">Registrations</th>
                  <td>{registrations}</td>
                </tr>
                <tr>
                  <th scope="row">Credit units</th>
                  <td>{creditUnits}</td>
                </tr>
                <tr>
                  <th scope="row">Teaching staff</th>
                  <td>{staff}</td>
                </tr>
                <tr>
                  <th scope="row">Semester</th>
                  <td>{semesterName ?? "—"}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* ---------------------------------------------------------- what you do */}
      <div className="grid grid--stats">
        {ACTIONS.map(({ href, tile, icon: Icon, title, text, cta }) => (
          <div className="card actioncard" key={href}>
            <span className={`figure__tile figure__tile--${tile}`}>
              <Icon size={20} />
            </span>
            <span className="actioncard__title">{title}</span>
            <span className="actioncard__text">{text}</span>
            <Link href={href} className="actioncard__link">
              {cta} →
            </Link>
          </div>
        ))}
      </div>

      {/* ------------------------------------ approval queue + notifications */}
      <div className="grid--split" style={{ marginBottom: "var(--gap)" }}>
        <div className="card">
          <div className="panel__head">
            <h2>Recent approval requests</h2>
            <Link href="/examinations" className="panel__link">
              View all →
            </Link>
          </div>
          {requests.length === 0 ? (
            <div className="empty-state">
              <span className="empty-state__title">Nothing awaiting your approval</span>
              <p className="muted">Grade appeals and leave requests for your department appear here.</p>
            </div>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Request type</th>
                    <th>Details</th>
                    <th>From</th>
                    <th>Date</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {requests.map((row) => (
                    <tr key={row.key}>
                      <td className="cell-primary">{row.type}</td>
                      <td className="text-sm">{row.detail}</td>
                      <td style={{ fontFamily: "var(--mono)" }} className="text-sm">
                        {row.by}
                      </td>
                      <td className="text-sm">{new Date(row.date).toLocaleDateString()}</td>
                      <td>
                        <span className="pill pill--pending">Pending</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="card">
          <div className="panel__head">
            <h2>Recent notifications</h2>
            <Link href="/communications" className="panel__link">
              View all →
            </Link>
          </div>
          {notices.length === 0 ? (
            <div className="empty-state">
              <span className="empty-state__title">No notices yet</span>
            </div>
          ) : (
            <ul className="notifs">
              {notices.map((item, index) => (
                <li key={item.id} className="notifs__item">
                  <span
                    className={`notifs__tile ${
                      index % 3 === 1 ? "notifs__tile--amber" : index % 3 === 2 ? "notifs__tile--purple" : "notifs__tile--blue"
                    }`}
                  >
                    {index % 3 === 0 ? <CheckCircleIcon size={15} /> : <MegaphoneIcon size={15} />}
                  </span>
                  <span className="notifs__body">
                    <span className="notifs__title">{item.title}</span>
                    <span className="notifs__text">{item.body}</span>
                    <span className="notifs__when">{new Date(item.sent_at).toLocaleDateString()}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </>
  );
}
