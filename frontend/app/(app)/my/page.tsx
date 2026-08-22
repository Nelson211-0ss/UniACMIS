"use client";

/**
 * Student dashboard (FR-STU-01…14 / checklist §4.16).
 *
 * Deliberately not a menu. The sidebar already lists every destination, so
 * repeating it here as a grid of tiles would cost a screenful and tell a
 * student nothing they could not already see. What this page answers instead is
 * "what do I need to do, and where do I stand" — computed from their real
 * record, so the page is different on the day fees fall due than it is the week
 * after registration closes.
 *
 * Colour carries meaning and nothing else: red is money owed or a blocked
 * result, orange is something approaching that needs attention, teal is settled.
 * A student who sees no red or orange has nothing outstanding.
 */

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  AlertCircleIcon,
  BarChartIcon,
  CalendarIcon,
  CheckCircleIcon,
  ClockIcon,
  CreditCardIcon,
  FileTextIcon,
  LayersIcon,
  MegaphoneIcon,
  UserPlusIcon,
} from "@/components/icons";
import { ApiFailure, api } from "@/lib/api";

import { useStudent } from "./student-context";

const DAY_LABELS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

/** The timetable stores 0 = Monday; `Date.getDay()` returns 0 = Sunday. */
function todayIndex() {
  return (new Date().getDay() + 6) % 7;
}

function hhmm(value: string) {
  return value.slice(0, 5);
}

interface Registration {
  id: number;
  course_code: string;
  course_title: string;
  credit_hours: number;
  status: string;
}

interface ClassEntry {
  id: number;
  course_code: string;
  course_title: string;
  room_code: string;
  lecturer_name: string;
  day_of_week: number;
  start_time: string;
  end_time: string;
}

interface Eligibility {
  percentage: string | null;
  threshold: string;
  below_threshold: boolean;
  waived: boolean;
  eligible: boolean;
}

type Severity = "critical" | "warning" | "info";

interface ActionItem {
  key: string;
  severity: Severity;
  text: string;
  href: string;
  cta: string;
}

export default function StudentDashboardPage() {
  const { student } = useStudent();

  const [semester, setSemester] = useState<{ id: number; name: string } | null>(null);
  const [registrationOpen, setRegistrationOpen] = useState(false);
  const [addDropOpen, setAddDropOpen] = useState(false);
  const [registrations, setRegistrations] = useState<Registration[]>([]);
  const [classes, setClasses] = useState<ClassEntry[]>([]);
  const [eligibility, setEligibility] = useState<Record<number, Eligibility>>({});
  const [gpa, setGpa] = useState<string | null>(null);
  const [resultsPublished, setResultsPublished] = useState(false);
  const [balance, setBalance] = useState<string | null>(null);
  const [currency, setCurrency] = useState("SSP");
  const [holds, setHolds] = useState<Array<{ message: string; blocking: boolean; source: string }>>([]);
  const [notices, setNotices] = useState<Array<{ id: number; title: string; body: string; sent_at: string }>>([]);
  const [loaded, setLoaded] = useState(false);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    if (!student) return;
    const me = student;
    let cancelled = false;

    async function load() {
      try {
        const calendar = await api.calendar();
        if (cancelled) return;
        setSemester(calendar.semester);
        setRegistrationOpen(calendar.registration_open);
        setAddDropOpen(calendar.add_drop_open);

        // Announcements are independent of the semester, so they load either way.
        void api
          .announcements("?page_size=3")
          .then((page) => !cancelled && setNotices(page.results))
          .catch(() => undefined);

        if (!calendar.semester) return;
        const semesterId = calendar.semester.id;

        const [registrationPage, result, feeBalance, clearance, timetable] = await Promise.all([
          api.myRegistrations(semesterId).catch(() => null),
          api.studentResult(me.id, semesterId).catch(() => null),
          api.myFeeBalance(me.id).catch(() => null),
          api.myClearance(me.id).catch(() => null),
          api.weeklyTimetable(semesterId).catch(() => null),
        ]);
        if (cancelled) return;

        const active = (registrationPage?.results ?? []).filter((r) => r.status === "registered");
        setRegistrations(active);
        if (result) {
          setResultsPublished(result.published && !result.withheld);
          setGpa(result.gpa);
        }
        if (feeBalance) {
          setBalance(feeBalance.balance);
          setCurrency(feeBalance.currency);
        }
        if (clearance) setHolds(clearance.holds);

        // Only the courses this student is actually taking appear on their
        // timetable — the endpoint returns the whole semester's grid.
        if (timetable) {
          const mine = new Set(active.map((r) => r.course_code));
          setClasses(timetable.results.filter((entry) => mine.has(entry.course_code)));
        }

        // Attendance is per registration, so it is a fan-out rather than one
        // call; a single course failing must not blank the others.
        const eligibilities = await Promise.all(
          active.map((r) =>
            api
              .examEligibility(r.id)
              .then((value): [number, Eligibility] | null => [r.id, value])
              .catch(() => null),
          ),
        );
        if (cancelled) return;
        setEligibility(Object.fromEntries(eligibilities.filter((entry) => entry !== null)));
      } catch (error) {
        if (error instanceof ApiFailure && error.offline) setOffline(true);
      } finally {
        if (!cancelled) setLoaded(true);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [student]);

  const credits = registrations.reduce((sum, r) => sum + r.credit_hours, 0);
  const owing = balance !== null && Number(balance) > 0;
  const atRisk = registrations.filter((r) => eligibility[r.id]?.eligible === false);
  // A fee balance shows up twice otherwise — once as its own figure, and again
  // as the finance hold it causes on clearance. Same fact, so say it once.
  const blockingHolds = holds.filter((h) => h.blocking && !(owing && h.source === "finance"));

  const todaysClasses = useMemo(() => {
    const today = todayIndex();
    return classes
      .filter((entry) => entry.day_of_week === today)
      .sort((a, b) => a.start_time.localeCompare(b.start_time));
  }, [classes]);

  const nextClass = useMemo(() => {
    const now = new Date().toTimeString().slice(0, 8);
    return todaysClasses.find((entry) => entry.end_time > now) ?? null;
  }, [todaysClasses]);

  /** The page's whole point: what actually needs doing, in severity order. */
  const actions = useMemo<ActionItem[]>(() => {
    if (!loaded) return [];
    const items: ActionItem[] = [];

    if (registrationOpen && registrations.length === 0) {
      items.push({
        key: "register",
        severity: "critical",
        text: "Registration is open and you have not registered for any courses yet.",
        href: "/my/courses",
        cta: "Register now",
      });
    }
    if (owing) {
      items.push({
        key: "fees",
        severity: "critical",
        text: `${Number(balance).toLocaleString()} ${currency} outstanding on your fees.`,
        href: "/my/finance",
        cta: "View invoices",
      });
    }
    if (blockingHolds.length > 0) {
      items.push({
        key: "holds",
        severity: "critical",
        text:
          blockingHolds.length === 1
            ? blockingHolds[0].message
            : `${blockingHolds.length} holds are blocking your clearance.`,
        href: "/documents",
        cta: "See holds",
      });
    }
    if (atRisk.length > 0) {
      items.push({
        key: "attendance",
        severity: "warning",
        text: `Attendance is below the required threshold in ${atRisk.length} ${
          atRisk.length === 1 ? "course" : "courses"
        } — you may be barred from those exams.`,
        href: "/my/attendance",
        cta: "Check attendance",
      });
    }
    if (addDropOpen && registrations.length > 0) {
      items.push({
        key: "adddrop",
        severity: "warning",
        text: "The add/drop window is still open — this is your last chance to change courses.",
        href: "/my/courses",
        cta: "Change courses",
      });
    }
    if (resultsPublished) {
      items.push({
        key: "results",
        severity: "info",
        text: "Your results for this semester have been published.",
        href: "/my/results",
        cta: "View results",
      });
    }
    return items;
  }, [
    loaded,
    registrationOpen,
    addDropOpen,
    registrations.length,
    owing,
    balance,
    currency,
    blockingHolds,
    atRisk.length,
    resultsPublished,
  ]);

  const firstName = student?.full_name.split(" ")[0] ?? "";


  const QUICK_ACCESS = [
    { href: "/my/courses", label: "Register Courses", icon: UserPlusIcon },
    { href: "/my/timetable", label: "View Timetable", icon: CalendarIcon },
    { href: "/my/finance", label: "Fees Statement", icon: CreditCardIcon },
    { href: "/my/results", label: "View Results", icon: LayersIcon },
    { href: "/documents", label: "My Documents", icon: FileTextIcon },
    { href: "/my/attendance", label: "Attendance", icon: ClockIcon },
  ];

  return (
    <>
      {/* ------------------------------------------------------- greeting */}
      <div className="page-header">
        <div>
          <h1>Welcome back, {firstName || "student"} 👋</h1>
          <p className="page-subtitle">
            {student?.programme_name ?? "Your programme"}
            {semester ? ` · Year ${student?.current_level ?? 1} · ${semester.name}` : ""}
          </p>
        </div>
        {student ? (
          <span className="idchip">
            <span className="idchip__label">Student ID</span>
            <span className="idchip__value">{student.student_id}</span>
          </span>
        ) : null}
      </div>

      {offline ? (
        <div className="alert alert--warning">
          <span>Working offline — figures below may be out of date.</span>
        </div>
      ) : null}

      {/* --------------------------------------------- what needs doing
        * Not in the reference design, but kept: it is the one part of this page
        * that changes with the student's situation rather than restating it. */}
      {loaded && actions.length > 0 ? (
        <section className="attention">
          <div className="attention__head">
            <AlertCircleIcon size={16} />
            <h2>Needs your attention</h2>
            <span className="attention__count">{actions.length}</span>
          </div>
          <ul className="attention__list">
            {actions.map((item) => (
              <li key={item.key} className={`attention__item attention__item--${item.severity}`}>
                <span className="attention__text">{item.text}</span>
                <Link href={item.href} className="attention__cta">
                  {item.cta} →
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {/* --------------------------------------------------------- figures */}
      <div className="grid grid--stats">
        <div className="card figure">
          <span className="figure__tile figure__tile--green">
            <CheckCircleIcon size={20} />
          </span>
          <span className="figure__label">Registration Status</span>
          <span className={`figure__value ${registrations.length > 0 ? "figure__value--green" : ""}`}>
            {!loaded ? "…" : registrations.length > 0 ? "Registered" : "Not registered"}
          </span>
          <span className="figure__meta">{semester ? semester.name : "No open semester"}</span>
          <Link href="/my/courses" className="figure__link">
            View Courses →
          </Link>
        </div>

        <div className="card figure">
          <span className="figure__tile figure__tile--red">
            <CreditCardIcon size={20} />
          </span>
          <span className="figure__label">Outstanding Fees</span>
          <span className={`figure__value ${owing ? "figure__value--red" : "figure__value--green"}`}>
            {!loaded || balance === null
              ? "…"
              : owing
                ? `${currency} ${Number(balance).toLocaleString()}`
                : "Cleared"}
          </span>
          <span className="figure__meta">{owing ? "Balance pending" : "Nothing owed"}</span>
          <Link href="/my/finance" className="figure__link">
            {owing ? "Make Payment →" : "View statement →"}
          </Link>
        </div>

        <div className="card figure">
          <span className="figure__tile figure__tile--blue">
            <CalendarIcon size={20} />
          </span>
          <span className="figure__label">Current Semester</span>
          <span className="figure__value">{semester ? semester.name : "—"}</span>
          <span className="figure__meta">{credits} credit units registered</span>
          <Link href="/my/timetable" className="figure__link">
            View Timetable →
          </Link>
        </div>

        <div className="card figure">
          <span className="figure__tile figure__tile--amber">
            <BarChartIcon size={20} />
          </span>
          <span className="figure__label">Academic Progress</span>
          <span className="figure__value">
            {!loaded ? "…" : resultsPublished ? (gpa ?? "—") : "—"}
          </span>
          <span className="figure__meta">
            {loaded && !resultsPublished ? "GPA pending publication" : "Cumulative GPA"}
          </span>
          <Link href="/my/results" className="figure__link">
            View Progress →
          </Link>
        </div>
      </div>

      {/* ------------------------------- today's classes + notifications */}
      <div className="duo">
        <div className="card">
          <div className="panel__head">
            <h2>Today&rsquo;s Classes</h2>
            <Link href="/my/timetable" className="panel__link">
              View Timetable →
            </Link>
          </div>
          {!loaded ? (
            <p className="muted">Loading…</p>
          ) : todaysClasses.length === 0 ? (
            <div className="empty-state">
              <span className="empty-state__title">No classes scheduled today</span>
              <p className="muted">
                {classes.length > 0
                  ? "Check your timetable for the rest of the week."
                  : "Nothing on your timetable for this semester yet."}
              </p>
            </div>
          ) : (
            <ul className="timeline">
              {todaysClasses.map((entry) => {
                const past = !nextClass || entry.end_time < nextClass.start_time;
                return (
                  <li key={entry.id} className={`timeline__item ${past && nextClass?.id !== entry.id ? "is-past" : ""}`}>
                    <div className="timeline__time">
                      {hhmm(entry.start_time)} – {hhmm(entry.end_time)}
                    </div>
                    <div className="timeline__title">{entry.course_title}</div>
                    <div className="timeline__meta">
                      {entry.course_code}
                      {entry.room_code ? ` · ${entry.room_code}` : ""}
                      {entry.lecturer_name ? ` · ${entry.lecturer_name}` : ""}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="card">
          <div className="panel__head">
            <h2>Recent Notifications</h2>
            <Link href="/communications" className="panel__link">
              View All →
            </Link>
          </div>
          {notices.length === 0 ? (
            <div className="empty-state">
              <span className="empty-state__title">No notices yet</span>
            </div>
          ) : (
            <ul className="notifs">
              {notices.map((notice, index) => (
                <li key={notice.id} className="notifs__item">
                  <span
                    className={`notifs__tile ${
                      index % 3 === 1 ? "notifs__tile--red" : index % 3 === 2 ? "notifs__tile--blue" : ""
                    }`}
                  >
                    <MegaphoneIcon size={15} />
                  </span>
                  <span className="notifs__body">
                    <span className="notifs__title">{notice.title}</span>
                    <span className="notifs__text">{notice.body}</span>
                    <span className="notifs__when">{new Date(notice.sent_at).toLocaleDateString()}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* ---------------------------------------------------- quick access */}
      <div className="card">
        <div className="panel__head">
          <h2>Quick Access</h2>
        </div>
        <div className="quickgrid">
          {QUICK_ACCESS.map(({ href, label, icon: Icon }) => (
            <Link key={href} href={href} className="quickgrid__item">
              <span className="quickgrid__tile">
                <Icon size={20} />
              </span>
              <span className="quickgrid__label">{label}</span>
            </Link>
          ))}
        </div>
      </div>

      {/* ------------------------------ semester overview + fee summary */}
      <div className="duo">
        <div className="card">
          <div className="panel__head">
            <h2>Semester Overview</h2>
          </div>
          <table className="detail">
            <tbody>
              <tr>
                <th scope="row">Semester</th>
                <td>{semester ? semester.name : "—"}</td>
              </tr>
              <tr>
                <th scope="row">Programme</th>
                <td>{student?.programme_code ?? "—"}</td>
              </tr>
              <tr>
                <th scope="row">Level</th>
                <td>Year {student?.current_level ?? "—"}</td>
              </tr>
              <tr>
                <th scope="row">Registered courses</th>
                <td>{registrations.length}</td>
              </tr>
              <tr>
                <th scope="row">Credit units</th>
                <td>{credits}</td>
              </tr>
              <tr>
                <th scope="row">Registration</th>
                <td className={registrationOpen ? "is-green" : ""}>
                  {registrationOpen ? "Open" : addDropOpen ? "Add/drop open" : "Closed"}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div className="card">
          <div className="panel__head">
            <h2>Fee Summary</h2>
            <Link href="/my/finance" className="panel__link">
              View Statement →
            </Link>
          </div>
          <table className="detail">
            <tbody>
              <tr>
                <th scope="row">Currency</th>
                <td>{currency}</td>
              </tr>
              <tr>
                <th scope="row">Outstanding balance</th>
                <td className={owing ? "is-red" : "is-green"}>
                  {balance === null ? "—" : `${currency} ${Number(balance).toLocaleString()}`}
                </td>
              </tr>
              <tr>
                <th scope="row">Clearance</th>
                <td className={holds.length === 0 ? "is-green" : "is-red"}>
                  {!loaded ? "—" : holds.length === 0 ? "Clear" : `${holds.length} hold(s)`}
                </td>
              </tr>
            </tbody>
          </table>
          <Link href="/my/finance" className="button primary block" style={{ marginTop: "var(--sp-4)" }}>
            {owing ? "Make Payment" : "View Statement"}
          </Link>
        </div>
      </div>

      {/* ------------------------------------- attendance per course */}
      {registrations.length > 0 ? (
        <div className="card">
          <div className="panel__head">
            <h2>Attendance by course</h2>
            <Link href="/my/attendance" className="panel__link">
              Full record →
            </Link>
          </div>
          <ul className="courselist">
            {registrations.map((registration) => {
              const elig = eligibility[registration.id];
              const percent =
                elig?.percentage !== null && elig?.percentage !== undefined ? Number(elig.percentage) : null;
              const threshold = elig ? Number(elig.threshold) : null;
              const tone =
                percent === null || threshold === null
                  ? "none"
                  : elig?.waived
                    ? "waived"
                    : percent >= threshold
                      ? "ok"
                      : percent >= threshold - 10
                        ? "warn"
                        : "bad";
              return (
                <li key={registration.id} className="courselist__item">
                  <div className="courselist__head">
                    <span className="courselist__code">{registration.course_code}</span>
                    <span className="courselist__title">{registration.course_title}</span>
                    <span className="courselist__credits">{registration.credit_hours} cr</span>
                  </div>
                  <div
                    className="courselist__meter"
                    role="img"
                    aria-label={percent === null ? "No attendance recorded yet" : `Attendance ${percent}%`}
                  >
                    <span
                      className={`courselist__fill courselist__fill--${tone}`}
                      style={{ width: `${percent ?? 0}%` }}
                    />
                  </div>
                  <div className="courselist__foot">
                    {percent === null ? (
                      <span className="muted">No attendance recorded yet</span>
                    ) : (
                      <>
                        <span className={`courselist__pct courselist__pct--${tone}`}>{percent}% attended</span>
                        {threshold !== null ? <span className="muted">{threshold}% required</span> : null}
                        {elig?.waived ? <span className="pill pill--info">Waived</span> : null}
                      </>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </>
  );
}
