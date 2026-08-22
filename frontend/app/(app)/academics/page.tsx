"use client";

/**
 * Institutional configuration (NFR-MAINT-03).
 *
 * The things a registrar must be able to change without a developer: the
 * institution's own details, the academic calendar (whose windows the
 * enrollment module then enforces), and the grading scale every transcript is
 * computed from.
 *
 * Two constraints are surfaced rather than hidden. Only one academic year and
 * one semester may be "current" at a time — enforced by a database constraint,
 * so the existing one must be cleared first rather than the new one silently
 * winning. And a grading scale is only usable when its bands cover 0–100
 * exactly with no gaps or overlaps, which is checked on demand instead of on
 * every keystroke, because a scale is necessarily incomplete while being built.
 */

import { useEffect, useState } from "react";

import { AlertCircleIcon, BuildingIcon, CalendarIcon, CheckCircleIcon, LayersIcon } from "@/components/icons";
import { ApiFailure, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Institution {
  id: number;
  name: string;
  short_name: string;
  mohest_code: string;
  default_currency: string;
  secondary_currency: string;
  address: string;
  phone: string;
  email: string;
  website: string;
  attendance_threshold_percent: string;
  timezone: string;
}

interface Semester {
  id: number;
  academic_year: number;
  academic_year_name: string;
  sequence: number;
  name: string;
  teaching_start: string;
  teaching_end: string;
  exam_start: string | null;
  exam_end: string | null;
  registration_opens: string | null;
  registration_closes: string | null;
  add_drop_closes: string | null;
  is_current: boolean;
  registration_open: boolean;
}

interface AcademicYear {
  id: number;
  name: string;
  start_date: string;
  end_date: string;
  is_current: boolean;
  semesters: Semester[];
}

interface Scale {
  id: number;
  name: string;
  max_grade_point: string;
  pass_grade_point: string;
  is_default: boolean;
  is_locked: boolean;
  bands: Array<{
    id: number;
    scale: number;
    letter: string;
    min_percent: string;
    max_percent: string;
    grade_point: string;
    is_pass: boolean;
    description: string;
  }>;
}

function errorText(error: unknown, fallback: string) {
  return error instanceof ApiFailure ? error.error.message : fallback;
}

/** `datetime-local` needs `YYYY-MM-DDTHH:mm`; the API returns full ISO. */
function toLocalInput(value: string | null) {
  return value ? value.slice(0, 16) : "";
}

export default function AcademicsPage() {
  const { can } = useAuth();
  const canManage = can("academics.change_semester");
  const canManageBands = can("academics.add_gradeband");

  const [institution, setInstitution] = useState<Institution | null>(null);
  const [years, setYears] = useState<AcademicYear[]>([]);
  const [scales, setScales] = useState<Scale[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "offline" | "error">("loading");
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  async function load() {
    try {
      const [inst, yearPage, scalePage] = await Promise.all([
        api.institution(),
        api.academicYears(),
        api.gradingScales().catch(() => ({ results: [] as Scale[] })),
      ]);
      setInstitution(inst[0] ?? null);
      // `academicYears()` returns the light shape; the detailed one carries
      // nested semesters, which is what the calendar section needs.
      setYears(yearPage.results as unknown as AcademicYear[]);
      setScales(scalePage.results);
      setState("ready");
    } catch (error) {
      setState(error instanceof ApiFailure && error.offline ? "offline" : "error");
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Calendar &amp; grading</h1>
          <p className="page-subtitle">Institution details, the academic calendar and grading scales</p>
        </div>
      </div>

      {notice ? (
        <div className={`alert alert--${notice.kind === "success" ? "success" : "error"}`}>
          <span>{notice.text}</span>
        </div>
      ) : null}
      {state === "offline" ? (
        <div className="alert alert--warning">
          <span>No connection. Showing whatever loaded earlier on this device.</span>
        </div>
      ) : null}
      {state === "error" ? (
        <div className="alert alert--error">
          <span>Could not load configuration. Try again shortly.</span>
        </div>
      ) : null}

      {institution ? (
        <InstitutionCard
          institution={institution}
          canManage={canManage}
          onNotice={setNotice}
          onChanged={() => void load()}
        />
      ) : null}

      <CalendarCard years={years} canManage={canManage} onNotice={setNotice} onChanged={() => void load()} />

      <GradingCard
        scales={scales}
        canManage={canManageBands}
        onNotice={setNotice}
        onChanged={() => void load()}
      />
    </>
  );
}

function InstitutionCard({
  institution,
  canManage,
  onNotice,
  onChanged,
}: {
  institution: Institution;
  canManage: boolean;
  onNotice: (n: { kind: "success" | "error"; text: string }) => void;
  onChanged: () => void;
}) {
  const [form, setForm] = useState(institution);
  const [busy, setBusy] = useState(false);

  useEffect(() => setForm(institution), [institution]);

  async function save() {
    setBusy(true);
    try {
      await api.updateInstitution(institution.id, {
        name: form.name,
        short_name: form.short_name,
        mohest_code: form.mohest_code,
        address: form.address,
        phone: form.phone,
        email: form.email,
        website: form.website,
        attendance_threshold_percent: form.attendance_threshold_percent,
      });
      onNotice({ kind: "success", text: "Institution details saved." });
      onChanged();
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not save the institution details.") });
    } finally {
      setBusy(false);
    }
  }

  function field(key: keyof Institution, label: string, width?: number) {
    return (
      <div className="field" style={width ? { width } : { flex: 1 }}>
        <label htmlFor={`inst-${key}`}>{label}</label>
        <input
          id={`inst-${key}`}
          value={String(form[key] ?? "")}
          disabled={!canManage}
          onChange={(event) => setForm((prev) => ({ ...prev, [key]: event.target.value }))}
        />
      </div>
    );
  }

  return (
    <div className="card">
      <div className="card__header">
        <span className="card__icon">
          <BuildingIcon size={18} />
        </span>
        <h2>Institution</h2>
      </div>
      <div className="field-row">
        {field("name", "Name")}
        {field("short_name", "Short name", 150)}
        {field("mohest_code", "MoHEST code", 150)}
      </div>
      <div className="field-row">
        {field("phone", "Phone", 180)}
        {field("email", "Email")}
        {field("website", "Website")}
      </div>
      <div className="field-row">
        {field("address", "Address")}
        {field("attendance_threshold_percent", "Attendance threshold %", 180)}
      </div>
      <p className="text-sm muted" style={{ margin: "0 0 12px" }}>
        Currency is {institution.default_currency}
        {institution.secondary_currency ? ` (secondary ${institution.secondary_currency})` : ""}, timezone{" "}
        {institution.timezone}. The attendance threshold is what the examinations office checks eligibility against.
      </p>
      {canManage ? (
        <button type="button" disabled={busy} onClick={() => void save()}>
          Save
        </button>
      ) : null}
    </div>
  );
}

function CalendarCard({
  years,
  canManage,
  onNotice,
  onChanged,
}: {
  years: AcademicYear[];
  canManage: boolean;
  onNotice: (n: { kind: "success" | "error"; text: string }) => void;
  onChanged: () => void;
}) {
  const [yearName, setYearName] = useState("");
  const [yearStart, setYearStart] = useState("");
  const [yearEnd, setYearEnd] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<Semester | null>(null);

  async function addYear() {
    if (!yearName.trim() || !yearStart || !yearEnd) return;
    setBusy(true);
    try {
      await api.createAcademicYear({ name: yearName.trim(), start_date: yearStart, end_date: yearEnd });
      onNotice({ kind: "success", text: "Academic year added." });
      setYearName("");
      setYearStart("");
      setYearEnd("");
      onChanged();
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not add the academic year.") });
    } finally {
      setBusy(false);
    }
  }

  async function makeCurrentYear(year: AcademicYear) {
    setBusy(true);
    try {
      const existing = years.find((y) => y.is_current && y.id !== year.id);
      // Only one row may be `is_current` at database level, so the outgoing one
      // is cleared first — otherwise the insert fails on the constraint rather
      // than the new year simply taking over.
      if (existing) await api.updateAcademicYear(existing.id, { is_current: false });
      await api.updateAcademicYear(year.id, { is_current: true });
      onNotice({ kind: "success", text: `${year.name} is now the current academic year.` });
      onChanged();
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not change the current year.") });
    } finally {
      setBusy(false);
    }
  }

  async function saveSemester() {
    if (!editing) return;
    setBusy(true);
    try {
      await api.updateSemester(editing.id, {
        registration_opens: editing.registration_opens || null,
        registration_closes: editing.registration_closes || null,
        add_drop_closes: editing.add_drop_closes || null,
        teaching_start: editing.teaching_start,
        teaching_end: editing.teaching_end,
        exam_start: editing.exam_start || null,
        exam_end: editing.exam_end || null,
      });
      onNotice({ kind: "success", text: `${editing.name} windows saved.` });
      setEditing(null);
      onChanged();
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not save those dates.") });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="section-title">Academic calendar</div>
      <div className="card">
        {canManage ? (
          <div className="field-row">
            <div className="field" style={{ width: 150 }}>
              <label htmlFor="ay-name">Year name</label>
              <input id="ay-name" value={yearName} onChange={(event) => setYearName(event.target.value)} placeholder="2027/2028" />
            </div>
            <div className="field" style={{ width: 170 }}>
              <label htmlFor="ay-start">Starts</label>
              <input id="ay-start" type="date" value={yearStart} onChange={(event) => setYearStart(event.target.value)} />
            </div>
            <div className="field" style={{ width: 170 }}>
              <label htmlFor="ay-end">Ends</label>
              <input id="ay-end" type="date" value={yearEnd} onChange={(event) => setYearEnd(event.target.value)} />
            </div>
            <div style={{ alignSelf: "flex-end" }}>
              <button type="button" disabled={busy} onClick={() => void addYear()}>
                Add year
              </button>
            </div>
          </div>
        ) : null}

        {years.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__title">No academic years configured</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Year</th>
                  <th>Dates</th>
                  <th>Semesters</th>
                  <th>Status</th>
                  {canManage ? <th /> : null}
                </tr>
              </thead>
              <tbody>
                {years.map((year) => (
                  <tr key={year.id}>
                    <td className="cell-primary">{year.name}</td>
                    <td className="text-sm">
                      {year.start_date} → {year.end_date}
                    </td>
                    <td className="text-sm">
                      {(year.semesters ?? []).map((s) => s.name).join(", ") || "—"}
                    </td>
                    <td>
                      {year.is_current ? <span className="pill pill--synced">Current</span> : <span className="muted text-sm">—</span>}
                    </td>
                    {canManage ? (
                      <td>
                        {!year.is_current ? (
                          <button type="button" className="sm ghost" disabled={busy} onClick={() => void makeCurrentYear(year)}>
                            Make current
                          </button>
                        ) : null}
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="section-title">Semester windows</div>
      <div className="card">
        <p className="text-sm muted" style={{ margin: "0 0 12px" }}>
          These windows are what course registration actually enforces — a student cannot register outside them, and the
          add/drop deadline must not fall before registration closes.
        </p>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Semester</th>
                <th>Teaching</th>
                <th>Registration</th>
                <th>Exams</th>
                <th>Open now</th>
                {canManage ? <th /> : null}
              </tr>
            </thead>
            <tbody>
              {years.flatMap((year) =>
                (year.semesters ?? []).map((semester) => (
                  <tr key={semester.id}>
                    <td className="cell-primary">
                      {semester.name}
                      <div className="text-sm muted">{year.name}</div>
                    </td>
                    <td className="text-sm">
                      {semester.teaching_start} → {semester.teaching_end}
                    </td>
                    <td className="text-sm">
                      {semester.registration_opens ? new Date(semester.registration_opens).toLocaleDateString() : "—"} →{" "}
                      {semester.registration_closes ? new Date(semester.registration_closes).toLocaleDateString() : "—"}
                    </td>
                    <td className="text-sm">
                      {semester.exam_start ?? "—"} → {semester.exam_end ?? "—"}
                    </td>
                    <td>
                      <span className={`pill ${semester.registration_open ? "pill--synced" : ""}`}>
                        {semester.registration_open ? "Registration open" : "Closed"}
                      </span>
                    </td>
                    {canManage ? (
                      <td>
                        <button type="button" className="sm secondary" onClick={() => setEditing(semester)}>
                          Edit dates
                        </button>
                      </td>
                    ) : null}
                  </tr>
                )),
              )}
            </tbody>
          </table>
        </div>
      </div>

      {editing ? (
        <div className="card">
          <div className="card__header">
            <span className="card__icon">
              <CalendarIcon size={18} />
            </span>
            <h2>
              {editing.name} — {editing.academic_year_name}
            </h2>
          </div>
          <div className="field-row">
            <div className="field">
              <label htmlFor="sem-tstart">Teaching starts</label>
              <input
                id="sem-tstart"
                type="date"
                value={editing.teaching_start}
                onChange={(event) => setEditing({ ...editing, teaching_start: event.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="sem-tend">Teaching ends</label>
              <input
                id="sem-tend"
                type="date"
                value={editing.teaching_end}
                onChange={(event) => setEditing({ ...editing, teaching_end: event.target.value })}
              />
            </div>
          </div>
          <div className="field-row">
            <div className="field">
              <label htmlFor="sem-ropen">Registration opens</label>
              <input
                id="sem-ropen"
                type="datetime-local"
                value={toLocalInput(editing.registration_opens)}
                onChange={(event) => setEditing({ ...editing, registration_opens: event.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="sem-rclose">Registration closes</label>
              <input
                id="sem-rclose"
                type="datetime-local"
                value={toLocalInput(editing.registration_closes)}
                onChange={(event) => setEditing({ ...editing, registration_closes: event.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="sem-adrop">Add/drop closes</label>
              <input
                id="sem-adrop"
                type="datetime-local"
                value={toLocalInput(editing.add_drop_closes)}
                onChange={(event) => setEditing({ ...editing, add_drop_closes: event.target.value })}
              />
            </div>
          </div>
          <div className="field-row">
            <div className="field">
              <label htmlFor="sem-estart">Exams start</label>
              <input
                id="sem-estart"
                type="date"
                value={editing.exam_start ?? ""}
                onChange={(event) => setEditing({ ...editing, exam_start: event.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="sem-eend">Exams end</label>
              <input
                id="sem-eend"
                type="date"
                value={editing.exam_end ?? ""}
                onChange={(event) => setEditing({ ...editing, exam_end: event.target.value })}
              />
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button type="button" disabled={busy} onClick={() => void saveSemester()}>
              Save dates
            </button>
            <button type="button" className="ghost" onClick={() => setEditing(null)}>
              Cancel
            </button>
          </div>
        </div>
      ) : null}
    </>
  );
}

function GradingCard({
  scales,
  canManage,
  onNotice,
  onChanged,
}: {
  scales: Scale[];
  canManage: boolean;
  onNotice: (n: { kind: "success" | "error"; text: string }) => void;
  onChanged: () => void;
}) {
  const [checks, setChecks] = useState<Record<number, { ok: boolean; errors: string[] }>>({});
  const [addFor, setAddFor] = useState<number | null>(null);
  const [letter, setLetter] = useState("");
  const [minPercent, setMinPercent] = useState("");
  const [maxPercent, setMaxPercent] = useState("");
  const [gradePoint, setGradePoint] = useState("");
  const [isPass, setIsPass] = useState(true);
  const [busy, setBusy] = useState(false);

  async function check(scaleId: number) {
    try {
      const result = await api.bandsCheck(scaleId);
      setChecks((prev) => ({ ...prev, [scaleId]: result }));
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not check that scale.") });
    }
  }

  async function addBand(scaleId: number) {
    if (!letter.trim() || !minPercent || !maxPercent || !gradePoint) return;
    setBusy(true);
    try {
      await api.addGradeBand({
        scale: scaleId,
        letter: letter.trim(),
        min_percent: minPercent,
        max_percent: maxPercent,
        grade_point: gradePoint,
        is_pass: isPass,
      });
      onNotice({ kind: "success", text: "Band added." });
      setLetter("");
      setMinPercent("");
      setMaxPercent("");
      setGradePoint("");
      onChanged();
      await check(scaleId);
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not add that band.") });
    } finally {
      setBusy(false);
    }
  }

  async function removeBand(id: number, scaleId: number) {
    try {
      await api.removeGradeBand(id);
      onNotice({ kind: "success", text: "Band removed." });
      onChanged();
      await check(scaleId);
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not remove that band.") });
    }
  }

  return (
    <>
      <div className="section-title">Grading scales</div>
      {scales.length === 0 ? (
        <div className="card">
          <div className="empty-state">
            <span className="empty-state__title">No grading scale configured</span>
          </div>
        </div>
      ) : (
        scales.map((scale) => {
          const result = checks[scale.id];
          return (
            <div className="card" key={scale.id}>
              <div className="card__header">
                <span className="card__icon">
                  <LayersIcon size={18} />
                </span>
                <h2>
                  {scale.name}
                  {scale.is_default ? <span className="pill pill--synced" style={{ marginLeft: 8 }}>Default</span> : null}
                  {scale.is_locked ? <span className="pill pill--pending" style={{ marginLeft: 6 }}>Locked</span> : null}
                </h2>
              </div>
              <p className="text-sm muted" style={{ margin: "0 0 12px" }}>
                Max grade point {scale.max_grade_point}, pass at {scale.pass_grade_point}.
                {scale.is_locked ? " Results already depend on this scale, so its bands cannot be changed." : ""}
              </p>

              {result ? (
                <div className={`alert alert--${result.ok ? "success" : "error"}`}>
                  {result.ok ? <CheckCircleIcon size={16} /> : <AlertCircleIcon size={16} />}
                  <span>{result.ok ? "Bands cover 0–100 with no gaps or overlaps." : result.errors.join(" ")}</span>
                </div>
              ) : null}

              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Grade</th>
                      <th>Range</th>
                      <th>Point</th>
                      <th>Pass</th>
                      {canManage && !scale.is_locked ? <th /> : null}
                    </tr>
                  </thead>
                  <tbody>
                    {scale.bands.map((band) => (
                      <tr key={band.id}>
                        <td className="cell-primary">{band.letter}</td>
                        <td>
                          {band.min_percent}–{band.max_percent}%
                        </td>
                        <td>{band.grade_point}</td>
                        <td>
                          <span className={`pill ${band.is_pass ? "pill--synced" : "pill--failed"}`}>
                            {band.is_pass ? "Pass" : "Fail"}
                          </span>
                        </td>
                        {canManage && !scale.is_locked ? (
                          <td>
                            <button type="button" className="sm ghost" onClick={() => void removeBand(band.id, scale.id)}>
                              Remove
                            </button>
                          </td>
                        ) : null}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                <button type="button" className="secondary" onClick={() => void check(scale.id)}>
                  Check coverage
                </button>
                {canManage && !scale.is_locked ? (
                  <button type="button" className="ghost" onClick={() => setAddFor(addFor === scale.id ? null : scale.id)}>
                    {addFor === scale.id ? "Cancel" : "Add a band"}
                  </button>
                ) : null}
              </div>

              {addFor === scale.id ? (
                <div className="field-row" style={{ marginTop: 12 }}>
                  <div className="field" style={{ width: 90 }}>
                    <label htmlFor="gb-letter">Grade</label>
                    <input id="gb-letter" value={letter} onChange={(event) => setLetter(event.target.value)} placeholder="A" />
                  </div>
                  <div className="field" style={{ width: 100 }}>
                    <label htmlFor="gb-min">Min %</label>
                    <input id="gb-min" value={minPercent} onChange={(event) => setMinPercent(event.target.value)} />
                  </div>
                  <div className="field" style={{ width: 100 }}>
                    <label htmlFor="gb-max">Max %</label>
                    <input id="gb-max" value={maxPercent} onChange={(event) => setMaxPercent(event.target.value)} />
                  </div>
                  <div className="field" style={{ width: 100 }}>
                    <label htmlFor="gb-point">Point</label>
                    <input id="gb-point" value={gradePoint} onChange={(event) => setGradePoint(event.target.value)} />
                  </div>
                  <div className="field" style={{ width: 110 }}>
                    <label htmlFor="gb-pass">Outcome</label>
                    <select id="gb-pass" value={isPass ? "pass" : "fail"} onChange={(event) => setIsPass(event.target.value === "pass")}>
                      <option value="pass">Pass</option>
                      <option value="fail">Fail</option>
                    </select>
                  </div>
                  <div style={{ alignSelf: "flex-end" }}>
                    <button type="button" disabled={busy} onClick={() => void addBand(scale.id)}>
                      Add
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          );
        })
      )}
    </>
  );
}
