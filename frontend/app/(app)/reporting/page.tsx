"use client";

/** Reporting & compliance (FR-RPT-01…05). A KPI dashboard built from a
 * fixed, documented set of reports (docs/TRACEABILITY.md D-18) — enrollment,
 * revenue and staff:student ratios — plus a per-course pass-rate lookup and
 * CSV/Excel export of the underlying tables. */

import { useEffect, useState } from "react";

import { BarChartCard } from "@/components/charts/BarChartCard";
import { DonutChartCard } from "@/components/charts/DonutChartCard";
import { LineChartCard } from "@/components/charts/LineChartCard";
import { CountUp } from "@/components/CountUp";
import { BarChartIcon, DownloadIcon } from "@/components/icons";
import { ApiFailure, api } from "@/lib/api";
import { CHART_STATUS } from "@/lib/chartColors";

interface EnrollmentData {
  total: number;
  by_gender: Record<string, number>;
  by_programme: Record<string, number>;
}

interface RevenueData {
  total_invoiced: string;
  net_billed: string;
  collected: string;
  outstanding: string;
}

interface RatiosData {
  students: number;
  staff: number;
  students_per_staff: number | null;
}

interface Widget {
  key: string;
  label: string;
  data: Record<string, unknown>;
}

const REPORTS = [
  { key: "student_register", label: "Student register (disaggregated)" },
  { key: "defaulters", label: "Fee defaulters" },
];

export default function ReportingPage() {
  const [widgets, setWidgets] = useState<Widget[]>([]);
  const [programmeNames, setProgrammeNames] = useState<Map<number, string>>(new Map());
  const [courses, setCourses] = useState<Array<{ id: number; code: string; title: string }>>([]);
  const [semesters, setSemesters] = useState<Array<{ id: number; name: string }>>([]);
  const [state, setState] = useState<"loading" | "ready" | "offline" | "error">("loading");
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  const [passCourse, setPassCourse] = useState("");
  const [passSemester, setPassSemester] = useState("");
  const [passResult, setPassResult] = useState<{
    passed: number;
    failed: number;
    incomplete: number;
    pass_rate_percent: number | null;
  } | null>(null);
  const [passTrend, setPassTrend] = useState<Array<{ semester: string; passRate: number | null }>>([]);

  const [reportKey, setReportKey] = useState(REPORTS[0].key);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    Promise.all([api.reportingDashboard(), api.programmes(), api.courses(), api.semesters()])
      .then(([dashboard, programmePage, coursePage, semesterPage]) => {
        setWidgets(dashboard);
        setProgrammeNames(new Map(programmePage.results.map((p) => [p.id, p.code])));
        setCourses(coursePage.results);
        setSemesters(semesterPage.results);
        setState("ready");
      })
      .catch((error) => setState(error instanceof ApiFailure && error.offline ? "offline" : "error"));
  }, []);

  useEffect(() => {
    if (!passCourse || semesters.length === 0) {
      setPassTrend([]);
      return;
    }
    let cancelled = false;
    Promise.all(
      semesters.map((semester) =>
        api
          .passRateReport(Number(passCourse), semester.id)
          .then((result) => ({ semester: semester.name, passRate: result.pass_rate_percent }))
          .catch(() => ({ semester: semester.name, passRate: null })),
      ),
    ).then((rows) => {
      if (!cancelled) setPassTrend(rows);
    });
    return () => {
      cancelled = true;
    };
  }, [passCourse, semesters]);

  async function lookupPassRate() {
    if (!passCourse || !passSemester) return;
    try {
      const result = await api.passRateReport(Number(passCourse), Number(passSemester));
      setPassResult(result);
    } catch (error) {
      setNotice({ kind: "error", text: error instanceof ApiFailure ? error.error.message : "Could not compute the pass rate." });
    }
  }

  async function download(format: "csv" | "xlsx") {
    setDownloading(true);
    try {
      await api.downloadReport(reportKey, format);
    } catch (error) {
      setNotice({ kind: "error", text: error instanceof ApiFailure ? error.error.message : "Could not export the report." });
    } finally {
      setDownloading(false);
    }
  }

  const enrollment = widgets.find((w) => w.key === "enrollment")?.data as EnrollmentData | undefined;
  const revenue = widgets.find((w) => w.key === "revenue")?.data as RevenueData | undefined;
  const ratios = widgets.find((w) => w.key === "ratios")?.data as RatiosData | undefined;

  const enrollmentByProgramme = enrollment
    ? Object.entries(enrollment.by_programme).map(([id, count]) => ({
        programme: programmeNames.get(Number(id)) ?? `#${id}`,
        students: count,
      }))
    : [];

  const genderSlices = enrollment
    ? Object.entries(enrollment.by_gender).map(([gender, count]) => ({
        key: gender,
        label: gender.replace(/_/g, " "),
        value: count,
      }))
    : [];

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Reports &amp; analytics</h1>
          <p className="page-subtitle">KPI dashboard, pass rates and exports</p>
        </div>
      </div>

      {notice ? (
        <div className={`alert alert--${notice.kind === "success" ? "success" : "error"}`}>
          <span>{notice.text}</span>
        </div>
      ) : null}
      {state === "offline" ? (
        <div className="alert alert--warning">
          <span>No connection — analytics need a live connection to compute.</span>
        </div>
      ) : null}
      {state === "error" ? (
        <div className="alert alert--error">
          <span>Could not load the dashboard. Try again shortly.</span>
        </div>
      ) : null}

      {ratios ? (
        <div className="grid">
          <div className="card stat stat--accent-blue">
            <div className="stat__top">
              <span className="stat__label">Active students</span>
              <span className="stat__icon">
                <BarChartIcon size={18} />
              </span>
            </div>
            <div className="stat__value">
              <CountUp value={ratios.students} />
            </div>
          </div>
          <div className="card stat stat--accent-teal">
            <div className="stat__top">
              <span className="stat__label">Active staff</span>
              <span className="stat__icon">
                <BarChartIcon size={18} />
              </span>
            </div>
            <div className="stat__value">
              <CountUp value={ratios.staff} />
            </div>
          </div>
          <div className="card stat stat--accent-purple">
            <div className="stat__top">
              <span className="stat__label">Students per staff</span>
              <span className="stat__icon">
                <BarChartIcon size={18} />
              </span>
            </div>
            <div className="stat__value">
              {ratios.students_per_staff !== null ? (
                <CountUp value={ratios.students_per_staff} decimals={1} />
              ) : (
                "—"
              )}
            </div>
          </div>
          {revenue ? (
            <div className="card stat stat--accent-red">
              <div className="stat__top">
                <span className="stat__label">Outstanding revenue</span>
                <span className="stat__icon">
                  <BarChartIcon size={18} />
                </span>
              </div>
              <div className="stat__value">
                <CountUp value={Number(revenue.outstanding)} />
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="grid--split">
        <BarChartCard
          title="Enrollment by programme"
          subtitle="Active students"
          data={enrollmentByProgramme}
          xKey="programme"
          series={[{ key: "students", label: "Students" }]}
        />
        <DonutChartCard
          title="Enrollment by gender"
          data={genderSlices}
          centre={enrollment ? { value: String(enrollment.total), label: "total" } : undefined}
        />
      </div>

      {revenue ? (
        <div className="grid--split">
          <DonutChartCard
            title="Revenue: collected vs outstanding"
            subtitle={`Net billed: ${Number(revenue.net_billed).toLocaleString()}`}
            data={[
              { key: "collected", label: "Collected", value: Number(revenue.collected), color: CHART_STATUS.good },
              { key: "outstanding", label: "Outstanding", value: Number(revenue.outstanding), color: CHART_STATUS.bad },
            ]}
          />
          <div className="card chart-card">
            <div className="chart-card__header">
              <div>
                <h3 className="chart-card__title">Pass rate lookup</h3>
                <p className="chart-card__subtitle">One course, one semester</p>
              </div>
            </div>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              <div className="field" style={{ flex: 1, minWidth: 160 }}>
                <label htmlFor="pass-course">Course</label>
                <select id="pass-course" value={passCourse} onChange={(event) => setPassCourse(event.target.value)}>
                  <option value="">Select a course</option>
                  {courses.map((course) => (
                    <option key={course.id} value={course.id}>
                      {course.code} — {course.title}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field" style={{ flex: 1, minWidth: 140 }}>
                <label htmlFor="pass-semester">Semester</label>
                <select id="pass-semester" value={passSemester} onChange={(event) => setPassSemester(event.target.value)}>
                  <option value="">Select a semester</option>
                  {semesters.map((semester) => (
                    <option key={semester.id} value={semester.id}>
                      {semester.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <button type="button" className="secondary" onClick={() => void lookupPassRate()}>
              Compute
            </button>
            {passResult ? (
              <div className="grid" style={{ marginTop: 4 }}>
                <div className="card stat stat--accent-teal" style={{ marginBottom: 0 }}>
                  <span className="stat__label">Pass rate</span>
                  <div className="stat__value">{passResult.pass_rate_percent ?? "—"}%</div>
                  <div className="stat__foot">
                    {passResult.passed} passed · {passResult.failed} failed · {passResult.incomplete} incomplete
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {passCourse ? (
        <LineChartCard
          title="Pass rate trend"
          subtitle={`${courses.find((c) => c.id === Number(passCourse))?.code ?? "Selected course"} across every semester`}
          data={passTrend}
          xKey="semester"
          series={[{ key: "passRate", label: "Pass rate" }]}
          unit="%"
          height={220}
        />
      ) : null}

      <div className="section-title">
        <DownloadIcon size={16} />
        Export a report
      </div>
      <div className="card" style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
        <div className="field" style={{ flex: 1, minWidth: 220, marginBottom: 0 }}>
          <label htmlFor="report-key">Report</label>
          <select id="report-key" value={reportKey} onChange={(event) => setReportKey(event.target.value)}>
            {REPORTS.map((report) => (
              <option key={report.key} value={report.key}>
                {report.label}
              </option>
            ))}
          </select>
        </div>
        <button type="button" className="secondary" disabled={downloading} onClick={() => void download("csv")}>
          Download CSV
        </button>
        <button type="button" className="secondary" disabled={downloading} onClick={() => void download("xlsx")}>
          Download Excel
        </button>
      </div>
    </>
  );
}
