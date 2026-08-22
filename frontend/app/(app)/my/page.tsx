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

import { CountUp } from "@/components/CountUp";
import {
  AlertCircleIcon,
  CalendarIcon,
  CheckCircleIcon,
  ClockIcon,
  CreditCardIcon,
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

  return (
    <>
      <div className="page-header">
        <div>
          <h1>{firstName ? `Hello, ${firstName}` : "My portal"}</h1>
          <p className="page-subtitle">
            {semester ? `${semester.name} · your standing right now` : "Your standing at a glance"}
          </p>
        </div>
        {semester ? (
          <span className={`pill ${registrationOpen ? "pill--synced" : ""}`}>
            {registrationOpen ? "Registration open" : addDropOpen ? "Add/drop open" : "Registration closed"}
          </span>
        ) : null}
      </div>

      {offline ? (
        <div className="alert alert--warning">
          <span>Working offline — figures below may be out of date.</span>
        </div>
      ) : null}

      {/* ---------------------------------------------- what needs doing */}
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

      {loaded && actions.length === 0 ? (
        <div className="attention attention--clear">
          <div className="attention__head">
            <CheckCircleIcon size={16} />
            <h2>You&rsquo;re all caught up</h2>
          </div>
          <p className="attention__clear-text">
            Nothing outstanding — no fees owing, no attendance warnings and no holds on your record.
          </p>
        </div>
      ) : null}

      {/* ---------------------------------------------------- at a glance */}
      <div className="grid grid--stats">
        <div className="card stat stat--accent-blue">
          <div className="stat__top">
            <span className="stat__label">Registered courses</span>
            <span className="stat__icon">
              <UserPlusIcon size={18} />
            </span>
          </div>
          <div className="stat__value">{loaded ? <CountUp value={registrations.length} duration={500} /> : "…"}</div>
          <div className="stat__foot">{credits} credit hours this semester</div>
        </div>

        <div className="card stat stat--accent-amber">
          <div className="stat__top">
            <span className="stat__label">Cumulative GPA</span>
            <span className="stat__icon">
              <LayersIcon size={18} />
            </span>
          </div>
          <div className="stat__value">{loaded ? (resultsPublished ? gpa ?? "—" : "—") : "…"}</div>
          <div className="stat__foot">
            {loaded && !resultsPublished ? "Not published for this semester yet" : "Across published results"}
          </div>
        </div>

        <div className={`card stat stat--accent-${owing ? "red" : "teal"}`}>
          <div className="stat__top">
            <span className="stat__label">Fee balance</span>
            <span className="stat__icon">
              <CreditCardIcon size={18} />
            </span>
          </div>
          <div className="stat__value">
            {!loaded || balance === null ? (
              "…"
            ) : owing ? (
              <>
                <CountUp value={Number(balance)} /> <span className="stat__unit">{currency}</span>
              </>
            ) : (
              "Clear"
            )}
          </div>
          <div className="stat__foot">{owing ? "Payable at the finance office" : "Nothing owed"}</div>
        </div>

        <div className={`card stat stat--accent-${atRisk.length > 0 ? "orange" : "teal"}`}>
          <div className="stat__top">
            <span className="stat__label">Exam eligibility</span>
            <span className="stat__icon">
              <ClockIcon size={18} />
            </span>
          </div>
          <div className="stat__value" style={{ fontSize: "1.5rem" }}>
            {!loaded
              ? "…"
              : registrations.length === 0
                ? "—"
                : atRisk.length === 0
                  ? "On track"
                  : `${atRisk.length} at risk`}
          </div>
          <div className="stat__foot">
            {registrations.length === 0 ? "No courses registered" : "Based on attendance so far"}
          </div>
        </div>
      </div>

      {/* -------------------------------------------------- today's classes */}
      {semester ? (
        <>
          <div className="section-title">
            <CalendarIcon size={14} /> {DAY_LABELS[todayIndex()]}&rsquo;s classes
          </div>
          <div className="card">
            {!loaded ? (
              <p className="muted">Loading…</p>
            ) : todaysClasses.length === 0 ? (
              <div className="empty-state">
                <span className="empty-state__title">No classes scheduled today</span>
                <p className="muted">
                  {classes.length > 0 ? (
                    <Link href="/my/timetable">See your full week →</Link>
                  ) : (
                    "Nothing on your timetable for this semester yet."
                  )}
                </p>
              </div>
            ) : (
              <ul className="daylist">
                {todaysClasses.map((entry) => {
                  const isNext = nextClass?.id === entry.id;
                  return (
                    <li key={entry.id} className={`daylist__item ${isNext ? "is-next" : ""}`}>
                      <span className="daylist__time">
                        {hhmm(entry.start_time)}
                        <span className="daylist__time-end">{hhmm(entry.end_time)}</span>
                      </span>
                      <span className="daylist__body">
                        <span className="daylist__course">
                          {entry.course_code} — {entry.course_title}
                        </span>
                        <span className="daylist__meta">
                          {entry.room_code || "Room TBC"}
                          {entry.lecturer_name ? ` · ${entry.lecturer_name}` : ""}
                        </span>
                      </span>
                      {isNext ? <span className="daylist__badge">Next</span> : null}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </>
      ) : null}

      {/* ------------------------------------------------------- my courses */}
      {registrations.length > 0 ? (
        <>
          <div className="section-title">This semester&rsquo;s courses</div>
          <div className="card">
            <ul className="courselist">
              {registrations.map((registration) => {
                const elig = eligibility[registration.id];
                const percent = elig?.percentage !== null && elig?.percentage !== undefined ? Number(elig.percentage) : null;
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
                    <div className="courselist__meter" role="img" aria-label={
                      percent === null ? "No attendance recorded yet" : `Attendance ${percent}%`
                    }>
                      <span className={`courselist__fill courselist__fill--${tone}`} style={{ width: `${percent ?? 0}%` }} />
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
        </>
      ) : null}

      {/* ---------------------------------------------------------- notices */}
      {notices.length > 0 ? (
        <>
          <div className="section-title">
            <MegaphoneIcon size={14} /> Latest notices
          </div>
          <div className="card">
            <ul className="noticelist">
              {notices.map((notice) => (
                <li key={notice.id} className="noticelist__item">
                  <span className="noticelist__title">{notice.title}</span>
                  <span className="noticelist__body">{notice.body}</span>
                  <span className="noticelist__date">{new Date(notice.sent_at).toLocaleDateString()}</span>
                </li>
              ))}
            </ul>
            <Link href="/communications" className="text-sm">
              All announcements →
            </Link>
          </div>
        </>
      ) : null}
    </>
  );
}
