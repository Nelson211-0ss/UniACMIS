"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { BarChartCard } from "@/components/charts/BarChartCard";
import { DonutChartCard } from "@/components/charts/DonutChartCard";
import { LineChartCard } from "@/components/charts/LineChartCard";
import { CountUp } from "@/components/CountUp";
import { Stamp } from "@/components/Stamp";
import { StatTile, StatTileSkeleton } from "@/components/StatTile";
import {
  BedIcon,
  BookOpenIcon,
  BriefcaseIcon,
  CalendarIcon,
  CheckCircleIcon,
  CreditCardIcon,
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

interface StudentSummary {
  id: number;
  full_name: string;
  student_id: string;
  programme_name: string;
  current_level: number;
  photo: string | null;
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export default function DashboardPage() {
  const router = useRouter();
  const { user, can, hasRole } = useAuth();
  const isStudent = hasRole("student");

  // A student's dashboard is `/my` and an applicant's is `/apply` — each
  // carries what that role actually came for. Keeping a staff dashboard here as
  // well would mean two homes, the second one showing them nothing they can use.
  const isApplicant = hasRole("applicant");
  const isHod = hasRole("hod");
  useEffect(() => {
    if (isStudent) router.replace("/my");
    else if (isApplicant) router.replace("/apply");
    else if (isHod) router.replace("/department");
  }, [isStudent, isApplicant, isHod, router]);
  const isFinanceStaff = hasRole("finance");
  const isLibraryStaff = hasRole("library");
  const isHrStaff = hasRole("hr");
  const isHostelStaff = hasRole("hostel");

  const [calendar, setCalendar] = useState<CalendarState | null>(null);
  const [calendarLoaded, setCalendarLoaded] = useState(false);
  const [studentCount, setStudentCount] = useState<number | null>(null);
  const [studentsLoaded, setStudentsLoaded] = useState(false);
  const [queued, setQueued] = useState(0);
  const [offline, setOffline] = useState(false);

  const [revenue, setRevenue] = useState<RevenueData | null>(null);
  const [enrollment, setEnrollment] = useState<EnrollmentData | null>(null);
  const [programmeNames, setProgrammeNames] = useState<Map<number, string>>(new Map());

  const [student, setStudent] = useState<StudentSummary | null>(null);
  const [photoFailed, setPhotoFailed] = useState(false);

  const [financeBalance, setFinanceBalance] = useState<number | null>(null);
  const [financeTrend, setFinanceTrend] = useState<Array<{ month: string; amount: number }>>([]);

  const [libraryStats, setLibraryStats] = useState<{ activeLoans: number; finesOwed: number } | null>(null);
  const [loanStatusSlices, setLoanStatusSlices] = useState<
    Array<{ key: string; label: string; value: number; color: string }>
  >([]);

  const [leaveStats, setLeaveStats] = useState<{ pending: number; total: number } | null>(null);

  const [hostelStats, setHostelStats] = useState<{ rooms: number; available: number; occupied: number } | null>(
    null,
  );

  const canSeeStudents = !isStudent && (user?.permissions.includes("registry.view_student") ?? false);
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

    if (isStudent) {
      api.myStudent().then(setStudent).catch(() => undefined);
    }

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

    if (isFinanceStaff) {
      Promise.all([api.invoices(), api.payments()])
        .then(([invoicePage, paymentPage]) => {
          setFinanceBalance(invoicePage.results.reduce((sum, invoice) => sum + Number(invoice.balance), 0));

          const byMonth = new Map<string, number>();
          for (const payment of paymentPage.results) {
            if (payment.status !== "confirmed" || !payment.confirmed_at) continue;
            const date = new Date(payment.confirmed_at);
            const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
            byMonth.set(key, (byMonth.get(key) ?? 0) + Number(payment.amount));
          }
          setFinanceTrend(
            Array.from(byMonth.entries())
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([key, amount]) => {
                const [year, month] = key.split("-");
                const label = new Date(Number(year), Number(month) - 1, 1).toLocaleDateString(undefined, {
                  month: "short",
                  year: "2-digit",
                });
                return { month: label, amount };
              }),
          );
        })
        .catch(() => undefined);
    }

    if (isLibraryStaff) {
      api
        .loans()
        .then((loanPage) => {
          const loans = loanPage.results;
          setLibraryStats({
            activeLoans: loans.filter((loan) => loan.status === "active").length,
            finesOwed: loans.reduce((sum, loan) => sum + Number(loan.owed), 0),
          });
          const counts = loans.reduce<Record<string, number>>((acc, loan) => {
            acc[loan.status] = (acc[loan.status] ?? 0) + 1;
            return acc;
          }, {});
          setLoanStatusSlices(
            Object.entries(counts).map(([status, count]) => ({
              key: status,
              label: status,
              value: count,
              color: status === "active" ? CHART_STATUS.warning : status === "lost" ? CHART_STATUS.bad : CHART_STATUS.good,
            })),
          );
        })
        .catch(() => undefined);
    }

    if (isHrStaff) {
      api
        .leaveRequests()
        .then((page) => {
          const rows = page.results;
          setLeaveStats({
            total: rows.length,
            pending: rows.filter((row) => row.status === "submitted" || row.status === "endorsed").length,
          });
        })
        .catch(() => undefined);
    }

    if (isHostelStaff) {
      api
        .rooms()
        .then((page) => {
          const rooms = page.results;
          setHostelStats({
            rooms: rooms.length,
            available: rooms.reduce((sum, room) => sum + room.available_beds, 0),
            occupied: rooms.reduce((sum, room) => sum + room.occupied_beds, 0),
          });
        })
        .catch(() => undefined);
    }

    return unsubscribe;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isStudent, canSeeStudents, canSeeAnalytics, isFinanceStaff, isLibraryStaff, isHrStaff, isHostelStaff]);

  const firstName = user?.full_name.split(" ")[0] ?? "";
  const links = visibleNav(can, hasRole).filter((item) => item.href !== "/dashboard" && item.href !== "/outbox");
  const sections = [...new Set(links.map((item) => item.section))];

  const enrollmentByProgramme = enrollment
    ? Object.entries(enrollment.by_programme).map(([id, count]) => ({
        programme: programmeNames.get(Number(id)) ?? `#${id}`,
        students: count,
      }))
    : [];

  const showPhoto = isStudent && !!student?.photo && !photoFailed;

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
        {showPhoto ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={student!.photo!} alt="" className="avatar" onError={() => setPhotoFailed(true)} />
        ) : (
          <span className="avatar" aria-hidden="true">
            {user ? initials(user.full_name) : "?"}
          </span>
        )}
      </div>

      {isStudent && student ? (
        <div className="card" style={{ display: "flex", alignItems: "center", gap: 20, flexWrap: "wrap" }}>
          {showPhoto ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={student.photo!} alt="" className="avatar avatar--lg" onError={() => setPhotoFailed(true)} />
          ) : (
            <span className="avatar avatar--lg" aria-hidden="true">
              {initials(student.full_name)}
            </span>
          )}
          <div style={{ minWidth: 0 }}>
            <h2>{student.full_name}</h2>
            <p className="muted" style={{ margin: "4px 0 0" }}>
              {student.student_id} &middot; {student.programme_name} &middot; Year {student.current_level}
            </p>
          </div>
          <Link href="/my" className="dashboard-section__link" style={{ marginLeft: "auto" }}>
            Full portal →
          </Link>
        </div>
      ) : null}

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
              value={studentCount !== null ? <CountUp value={studentCount} /> : "—"}
              icon={<UsersIcon size={18} />}
              accent="blue"
            />
          )
        ) : null}

        {revenue ? (
          <StatTile
            label="Outstanding revenue"
            value={<CountUp value={Number(revenue.outstanding)} />}
            icon={<CreditCardIcon size={18} />}
            accent="red"
            foot={`Net billed ${Number(revenue.net_billed).toLocaleString()}`}
          />
        ) : null}

        <StatTile
          label="Offline queue on this device"
          value={<CountUp value={queued} duration={500} />}
          icon={<InboxIcon size={18} />}
          accent="amber"
          foot={
            queued > 0 ? "Stored on this device — will send automatically" : "Nothing waiting"
          }
        />
      </div>

      {calendarLoaded && calendar?.configured ? (
        <div className="card" style={{ display: "flex", alignItems: "center", gap: 24, flexWrap: "wrap" }}>
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

      {isFinanceStaff ? (
        <>
          <div className="dashboard-section">
            <h2>Finance</h2>
            <Link href="/finance" className="dashboard-section__link">
              Open finance →
            </Link>
          </div>
          <div className="grid--split">
            <div className="card stat stat--accent-blue">
              <div className="stat__top">
                <span className="stat__label">Outstanding balance</span>
                <span className="stat__icon">
                  <CreditCardIcon size={18} />
                </span>
              </div>
              <div className="stat__value">
                {financeBalance !== null ? <CountUp value={financeBalance} /> : "—"}
              </div>
            </div>
            <LineChartCard
              title="Payments collected by month"
              subtitle="Confirmed payments only"
              data={financeTrend}
              xKey="month"
              series={[{ key: "amount", label: "Collected" }]}
              height={200}
            />
          </div>
        </>
      ) : null}

      {isLibraryStaff ? (
        <>
          <div className="dashboard-section">
            <h2>Library</h2>
            <Link href="/library" className="dashboard-section__link">
              Open library →
            </Link>
          </div>
          <div className="grid--split">
            <div className="grid">
              <div className="card stat stat--accent-amber">
                <div className="stat__top">
                  <span className="stat__label">Active loans</span>
                  <span className="stat__icon">
                    <BookOpenIcon size={18} />
                  </span>
                </div>
                <div className="stat__value">
                  {libraryStats ? <CountUp value={libraryStats.activeLoans} /> : "—"}
                </div>
              </div>
              <div className="card stat stat--accent-red">
                <div className="stat__top">
                  <span className="stat__label">Fines outstanding</span>
                  <span className="stat__icon">
                    <BookOpenIcon size={18} />
                  </span>
                </div>
                <div className="stat__value">
                  {libraryStats ? <CountUp value={libraryStats.finesOwed} /> : "—"}
                </div>
              </div>
            </div>
            <DonutChartCard title="Loan status" data={loanStatusSlices} innerRadius={0} height={200} />
          </div>
        </>
      ) : null}

      {isHrStaff ? (
        <>
          <div className="dashboard-section">
            <h2>HR &amp; leave</h2>
            <Link href="/hr" className="dashboard-section__link">
              Open HR →
            </Link>
          </div>
          <div className="grid">
            <div className="card stat stat--accent-orange">
              <div className="stat__top">
                <span className="stat__label">Leave requests awaiting action</span>
                <span className="stat__icon">
                  <BriefcaseIcon size={18} />
                </span>
              </div>
              <div className="stat__value">
                {leaveStats ? <CountUp value={leaveStats.pending} duration={500} /> : "—"}
              </div>
            </div>
            <div className="card stat stat--accent-teal">
              <div className="stat__top">
                <span className="stat__label">Total leave requests</span>
                <span className="stat__icon">
                  <BriefcaseIcon size={18} />
                </span>
              </div>
              <div className="stat__value">
                {leaveStats ? <CountUp value={leaveStats.total} duration={500} /> : "—"}
              </div>
            </div>
          </div>
        </>
      ) : null}

      {isHostelStaff ? (
        <>
          <div className="dashboard-section">
            <h2>Hostel</h2>
            <Link href="/hostel" className="dashboard-section__link">
              Open hostel →
            </Link>
          </div>
          <div className="grid--split">
            <div className="grid">
              <div className="card stat stat--accent-blue">
                <div className="stat__top">
                  <span className="stat__label">Rooms</span>
                  <span className="stat__icon">
                    <BedIcon size={18} />
                  </span>
                </div>
                <div className="stat__value">
                  {hostelStats ? <CountUp value={hostelStats.rooms} duration={500} /> : "—"}
                </div>
              </div>
              <div className="card stat stat--accent-teal">
                <div className="stat__top">
                  <span className="stat__label">Available beds</span>
                  <span className="stat__icon">
                    <BedIcon size={18} />
                  </span>
                </div>
                <div className="stat__value">
                  {hostelStats ? <CountUp value={hostelStats.available} duration={500} /> : "—"}
                </div>
              </div>
            </div>
            <DonutChartCard
              title="Bed occupancy"
              data={[
                { key: "occupied", label: "Occupied", value: hostelStats?.occupied ?? 0, color: CHART_STATUS.warning },
                { key: "available", label: "Available", value: hostelStats?.available ?? 0, color: CHART_STATUS.good },
              ]}
              height={200}
            />
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
