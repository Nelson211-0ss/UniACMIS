"use client";

/**
 * Admissions (FR-ADM-01…08).
 *
 * The pipeline in one place: intake (including a paper form keyed in by staff,
 * which the API marks `staff_entry` automatically), scoring by the committee,
 * the merit list with its quota rules, the offer decision, and conversion into
 * a real student record.
 *
 * Two rules from the backend shape this page and are surfaced rather than
 * hidden: an application cannot be submitted until its fee is confirmed, and
 * only a *draft* can be edited at all — everything after that moves through a
 * named action, so there is no generic "edit" button on a submitted row.
 */

import { useEffect, useState } from "react";

import { CreditCardIcon, LayersIcon, UserPlusIcon } from "@/components/icons";
import { ApiFailure, api } from "@/lib/api";
import type { ApplicationDetail } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Row {
  id: number;
  reference_number: string;
  full_name: string;
  programme: number;
  programme_code: string;
  status: string;
  score: string | null;
  fee_paid: boolean;
  created_at: string;
}

const STATUS_PILL: Record<string, string> = {
  draft: "",
  submitted: "pill--pending",
  under_review: "pill--info",
  offered: "pill--info",
  accepted: "pill--synced",
  enrolled: "pill--synced",
  rejected: "pill--failed",
  withdrawn: "pill--failed",
};

const GENDERS = ["female", "male"];

function errorText(error: unknown, fallback: string) {
  return error instanceof ApiFailure ? error.error.message : fallback;
}

export default function AdmissionsPage() {
  const { can } = useAuth();
  const canAdd = can("admissions.add_application");
  const canReview = can("admissions.add_applicationreview");
  const canDecide = can("admissions.decide_application");
  const canTakeFee = can("admissions.add_applicationfeepayment");
  const canConfirmFee = can("admissions.change_applicationfeepayment");

  const [rows, setRows] = useState<Row[]>([]);
  const [programmes, setProgrammes] = useState<Array<{ id: number; code: string; name: string }>>([]);
  const [years, setYears] = useState<Array<{ id: number; name: string }>>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [state, setState] = useState<"loading" | "ready" | "offline" | "error">("loading");
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<ApplicationDetail | null>(null);

  async function load() {
    try {
      const params = statusFilter ? `?page_size=100&status=${statusFilter}` : "?page_size=100";
      const [appPage, programmePage, yearPage] = await Promise.all([
        api.applications(params),
        api.programmes(),
        api.academicYears(),
      ]);
      setRows(appPage.results);
      setProgrammes(programmePage.results);
      setYears(yearPage.results);
      setState("ready");
    } catch (error) {
      setState(error instanceof ApiFailure && error.offline ? "offline" : "error");
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  async function openDetail(id: number) {
    if (open?.id === id) {
      setOpen(null);
      return;
    }
    try {
      setOpen(await api.application(id));
    } catch (error) {
      setNotice({ kind: "error", text: errorText(error, "Could not load that application.") });
    }
  }

  /** `success` may be a function of the result, for actions whose outcome is not
   * settled by the call succeeding — confirming a fee polls the payment
   * provider, and "still pending" is a normal answer, not a failure. */
  async function act(fn: () => Promise<unknown>, success: string | ((result: never) => string)) {
    setBusy(true);
    setNotice(null);
    try {
      const result = await fn();
      const text = typeof success === "function" ? success(result as never) : success;
      setNotice({ kind: "success", text });
      await load();
      if (open) setOpen(await api.application(open.id));
    } catch (error) {
      setNotice({ kind: "error", text: errorText(error, "That action could not be completed.") });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Admissions</h1>
          <p className="page-subtitle">Applications, review, merit lists and offers</p>
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
          <span>Could not load applications. Try again shortly.</span>
        </div>
      ) : null}

      {canAdd ? (
        <NewApplicationCard
          programmes={programmes}
          years={years}
          onNotice={setNotice}
          onCreated={() => void load()}
        />
      ) : null}

      {canDecide ? <MeritListCard programmes={programmes} years={years} onNotice={setNotice} /> : null}

      <div className="section-title">Applications</div>
      <div className="card">
        <div className="field" style={{ maxWidth: 240 }}>
          <label htmlFor="adm-status">Status</label>
          <select id="adm-status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="">All</option>
            {Object.keys(STATUS_PILL).map((value) => (
              <option key={value} value={value}>
                {value.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </div>

        {state === "loading" ? (
          <p className="muted">Loading…</p>
        ) : rows.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__title">No applications</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Reference</th>
                  <th>Applicant</th>
                  <th>Programme</th>
                  <th>Status</th>
                  <th>Score</th>
                  <th>Fee</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td style={{ fontFamily: "var(--mono)" }} className="text-sm">
                      {row.reference_number}
                    </td>
                    <td className="cell-primary">{row.full_name}</td>
                    <td>{row.programme_code}</td>
                    <td>
                      <span className={`pill ${STATUS_PILL[row.status] ?? ""}`}>
                        {row.status.replace(/_/g, " ")}
                      </span>
                    </td>
                    <td>{row.score ?? "—"}</td>
                    <td>
                      <span className={`pill ${row.fee_paid ? "pill--synced" : "pill--pending"}`}>
                        {row.fee_paid ? "Paid" : "Unpaid"}
                      </span>
                    </td>
                    <td>
                      <button type="button" className="sm secondary" onClick={() => void openDetail(row.id)}>
                        {open?.id === row.id ? "Close" : "Open"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {open ? (
        <ApplicationDetailCard
          application={open}
          busy={busy}
          canReview={canReview}
          canDecide={canDecide}
          canTakeFee={canTakeFee}
          canConfirmFee={canConfirmFee}
          onAct={act}
        />
      ) : null}
    </>
  );
}

function NewApplicationCard({
  programmes,
  years,
  onNotice,
  onCreated,
}: {
  programmes: Array<{ id: number; code: string; name: string }>;
  years: Array<{ id: number; name: string }>;
  onNotice: (n: { kind: "success" | "error"; text: string }) => void;
  onCreated: () => void;
}) {
  const [programme, setProgramme] = useState<number | "">("");
  const [year, setYear] = useState<number | "">("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [gender, setGender] = useState("female");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [previousGrade, setPreviousGrade] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const current = years[0];
    if (current) setYear(current.id);
  }, [years]);

  async function create() {
    if (!programme || !year || !firstName.trim() || !lastName.trim() || !phone.trim()) {
      onNotice({ kind: "error", text: "Programme, intake year, both names and a phone number are required." });
      return;
    }
    setBusy(true);
    try {
      await api.createApplication({
        programme: Number(programme),
        intended_academic_year: Number(year),
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        gender,
        phone: phone.trim(),
        email: email.trim(),
        previous_grade: previousGrade.trim(),
      });
      onNotice({ kind: "success", text: "Application recorded as a draft. Take the fee, then submit it." });
      setFirstName("");
      setLastName("");
      setPhone("");
      setEmail("");
      setPreviousGrade("");
      onCreated();
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not record the application.") });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <div className="card__header">
        <span className="card__icon">
          <UserPlusIcon size={18} />
        </span>
        <h2>Record an application</h2>
      </div>
      <p className="text-sm muted" style={{ margin: "0 0 12px" }}>
        For a paper form taken at the counter. It is filed as a draft — the fee must be confirmed before it can be
        submitted for review.
      </p>
      <div className="field-row">
        <div className="field" style={{ flex: 2 }}>
          <label htmlFor="na-programme">Programme</label>
          <select id="na-programme" value={programme} onChange={(event) => setProgramme(event.target.value ? Number(event.target.value) : "")}>
            <option value="">Select…</option>
            {programmes.map((p) => (
              <option key={p.id} value={p.id}>
                {p.code} — {p.name}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="na-year">Intake year</label>
          <select id="na-year" value={year} onChange={(event) => setYear(event.target.value ? Number(event.target.value) : "")}>
            <option value="">Select…</option>
            {years.map((y) => (
              <option key={y.id} value={y.id}>
                {y.name}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="field-row">
        <div className="field">
          <label htmlFor="na-first">First name</label>
          <input id="na-first" value={firstName} onChange={(event) => setFirstName(event.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="na-last">Last name</label>
          <input id="na-last" value={lastName} onChange={(event) => setLastName(event.target.value)} />
        </div>
        <div className="field" style={{ width: 120 }}>
          <label htmlFor="na-gender">Gender</label>
          <select id="na-gender" value={gender} onChange={(event) => setGender(event.target.value)}>
            {GENDERS.map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="field-row">
        <div className="field">
          <label htmlFor="na-phone">Phone</label>
          <input id="na-phone" value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="+211…" />
        </div>
        <div className="field">
          <label htmlFor="na-email">Email</label>
          <input id="na-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
        </div>
        <div className="field" style={{ width: 140 }}>
          <label htmlFor="na-grade">Previous grade</label>
          <input id="na-grade" value={previousGrade} onChange={(event) => setPreviousGrade(event.target.value)} placeholder="B" />
        </div>
      </div>
      <button type="button" disabled={busy} onClick={() => void create()}>
        Record application
      </button>
    </div>
  );
}

function MeritListCard({
  programmes,
  years,
  onNotice,
}: {
  programmes: Array<{ id: number; code: string; name: string }>;
  years: Array<{ id: number; name: string }>;
  onNotice: (n: { kind: "success" | "error"; text: string }) => void;
}) {
  const [programme, setProgramme] = useState<number | "">("");
  const [year, setYear] = useState<number | "">("");
  const [entries, setEntries] = useState<Array<{
    application_id: number;
    reference_number: string;
    full_name: string;
    rank: number;
    score: string | null;
    admitted: boolean;
    quota_category: string | null;
  }> | null>(null);

  useEffect(() => {
    const current = years[0];
    if (current) setYear(current.id);
  }, [years]);

  async function build() {
    if (!programme || !year) return;
    try {
      setEntries(await api.meritList(Number(programme), Number(year)));
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not build the merit list.") });
    }
  }

  return (
    <div className="card">
      <div className="card__header">
        <span className="card__icon">
          <LayersIcon size={18} />
        </span>
        <h2>Merit list</h2>
      </div>
      <p className="text-sm muted" style={{ margin: "0 0 12px" }}>
        Ranked by score, with reserved quota seats filled first. Rank is overall merit — an unadmitted applicant still
        shows their true position.
      </p>
      <div className="field-row">
        <div className="field" style={{ flex: 2 }}>
          <label htmlFor="ml-programme">Programme</label>
          <select id="ml-programme" value={programme} onChange={(event) => setProgramme(event.target.value ? Number(event.target.value) : "")}>
            <option value="">Select…</option>
            {programmes.map((p) => (
              <option key={p.id} value={p.id}>
                {p.code} — {p.name}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="ml-year">Intake year</label>
          <select id="ml-year" value={year} onChange={(event) => setYear(event.target.value ? Number(event.target.value) : "")}>
            <option value="">Select…</option>
            {years.map((y) => (
              <option key={y.id} value={y.id}>
                {y.name}
              </option>
            ))}
          </select>
        </div>
        <div style={{ alignSelf: "flex-end" }}>
          <button type="button" disabled={!programme || !year} onClick={() => void build()}>
            Build
          </button>
        </div>
      </div>

      {entries !== null ? (
        entries.length === 0 ? (
          <p className="muted">No scored applications for this programme and intake yet.</p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Applicant</th>
                  <th>Score</th>
                  <th>Quota</th>
                  <th>Outcome</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr key={entry.application_id}>
                    <td>{entry.rank}</td>
                    <td className="cell-primary">
                      {entry.full_name}
                      <div className="text-sm muted" style={{ fontFamily: "var(--mono)" }}>
                        {entry.reference_number}
                      </div>
                    </td>
                    <td>{entry.score ?? "—"}</td>
                    <td className="text-sm">{entry.quota_category ?? "General"}</td>
                    <td>
                      <span className={`pill ${entry.admitted ? "pill--synced" : ""}`}>
                        {entry.admitted ? "Admitted" : "Not admitted"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : null}
    </div>
  );
}

function ApplicationDetailCard({
  application,
  busy,
  canReview,
  canDecide,
  canTakeFee,
  canConfirmFee,
  onAct,
}: {
  application: ApplicationDetail;
  busy: boolean;
  canReview: boolean;
  canDecide: boolean;
  canTakeFee: boolean;
  canConfirmFee: boolean;
  onAct: (fn: () => Promise<unknown>, success: string | ((result: never) => string)) => Promise<void>;
}) {
  const [score, setScore] = useState("");
  const [comments, setComments] = useState("");
  const [reason, setReason] = useState("");
  const [feeAmount, setFeeAmount] = useState("500");

  const status = application.status;
  const pendingFee = application.fee_payments.find((p) => p.status === "pending");

  return (
    <div className="card">
      <div className="card__header">
        <h2>
          {application.full_name}{" "}
          <span className="pill" style={{ marginLeft: 6 }}>
            {status.replace(/_/g, " ")}
          </span>
        </h2>
      </div>

      <div className="grid grid--compact" style={{ marginBottom: 16 }}>
        <div>
          <div className="text-sm muted">Reference</div>
          <div style={{ fontFamily: "var(--mono)" }}>{application.reference_number}</div>
        </div>
        <div>
          <div className="text-sm muted">Programme</div>
          <div>{application.programme_code}</div>
        </div>
        <div>
          <div className="text-sm muted">Phone</div>
          <div>{application.phone || "—"}</div>
        </div>
        <div>
          <div className="text-sm muted">Previous grade</div>
          <div>{application.previous_grade || "—"}</div>
        </div>
        <div>
          <div className="text-sm muted">Average score</div>
          <div>{application.score ?? "Not scored"}</div>
        </div>
        <div>
          <div className="text-sm muted">Source</div>
          <div>{application.source.replace(/_/g, " ")}</div>
        </div>
      </div>

      {application.decision_reason ? (
        <div className="alert alert--info">
          <span>{application.decision_reason}</span>
        </div>
      ) : null}

      {/* --- fee: gates `submit`, so it comes first --- */}
      {!application.fee_paid && (canTakeFee || canConfirmFee) ? (
        <div style={{ marginBottom: 16 }}>
          <div className="section-title" style={{ marginTop: 0 }}>
            <CreditCardIcon size={14} /> Application fee
          </div>
          <p className="text-sm muted" style={{ margin: "0 0 8px" }}>
            The fee must be confirmed before this application can be submitted for review.
          </p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
            {!pendingFee && canTakeFee ? (
              <>
                <div className="field" style={{ width: 120, marginBottom: 0 }}>
                  <label htmlFor="fee-amount">Amount</label>
                  <input id="fee-amount" value={feeAmount} onChange={(event) => setFeeAmount(event.target.value)} />
                </div>
                <button
                  type="button"
                  className="secondary"
                  disabled={busy}
                  onClick={() => void onAct(() => api.initiateApplicationFee(application.id, feeAmount), "Fee recorded as pending.")}
                >
                  Record fee
                </button>
              </>
            ) : null}
            {pendingFee && canConfirmFee ? (
              <>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    void onAct(
                      () => api.confirmApplicationFee(application.id, pendingFee.reference),
                      // The provider is polled, never assumed — report what it
                      // actually said rather than treating a successful call as
                      // a settled payment.
                      (result: { status: string }) =>
                        result.status === "confirmed"
                          ? "Fee confirmed."
                          : result.status === "failed"
                            ? "The provider reports this payment failed."
                            : "Still pending with the provider — check again in a moment.",
                    )
                  }
                >
                  Check {pendingFee.amount} {pendingFee.currency}
                </button>
                <span className="text-sm muted">
                  Reference {pendingFee.reference}
                </span>
              </>
            ) : null}
          </div>
        </div>
      ) : null}

      {/* --- submit / withdraw --- */}
      {status === "draft" ? (
        <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
          <button
            type="button"
            disabled={busy || !application.fee_paid}
            onClick={() => void onAct(() => api.submitApplication(application.id), "Application submitted for review.")}
          >
            Submit for review
          </button>
          {!application.fee_paid ? <span className="text-sm muted">Confirm the fee first.</span> : null}
        </div>
      ) : null}

      {/* --- scoring --- */}
      {canReview && (status === "submitted" || status === "under_review") ? (
        <div style={{ marginBottom: 16 }}>
          <div className="section-title" style={{ marginTop: 0 }}>
            Score this application
          </div>
          <div className="field-row">
            <div className="field" style={{ width: 110 }}>
              <label htmlFor="rev-score">Score</label>
              <input id="rev-score" value={score} onChange={(event) => setScore(event.target.value)} />
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label htmlFor="rev-comments">Comments</label>
              <input id="rev-comments" value={comments} onChange={(event) => setComments(event.target.value)} />
            </div>
            <div style={{ alignSelf: "flex-end" }}>
              <button
                type="button"
                disabled={busy || score.trim() === ""}
                onClick={() =>
                  void onAct(() => api.reviewApplication(application.id, score, comments), "Score recorded.").then(() => {
                    setScore("");
                    setComments("");
                  })
                }
              >
                Record score
              </button>
            </div>
          </div>
          {application.reviews.length > 0 ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Reviewer</th>
                    <th>Score</th>
                    <th>Comments</th>
                  </tr>
                </thead>
                <tbody>
                  {application.reviews.map((review) => (
                    <tr key={review.id}>
                      <td className="cell-primary">{review.reviewer_name}</td>
                      <td>{review.score}</td>
                      <td className="text-sm muted">{review.comments || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      ) : null}

      {/* --- decision --- */}
      {canDecide && (status === "submitted" || status === "under_review") ? (
        <div style={{ marginBottom: 16 }}>
          <div className="section-title" style={{ marginTop: 0 }}>
            Decision
          </div>
          <div className="field-row">
            <div className="field" style={{ flex: 1 }}>
              <label htmlFor="dec-reason">Reason (recorded and sent to the applicant)</label>
              <input id="dec-reason" value={reason} onChange={(event) => setReason(event.target.value)} />
            </div>
            <div style={{ alignSelf: "flex-end", display: "flex", gap: 8 }}>
              <button
                type="button"
                disabled={busy || reason.trim().length < 5}
                onClick={() => void onAct(() => api.decideApplication(application.id, "offered", reason), "Offer made.")}
              >
                Offer
              </button>
              <button
                type="button"
                className="danger"
                disabled={busy || reason.trim().length < 5}
                onClick={() => void onAct(() => api.decideApplication(application.id, "rejected", reason), "Application rejected.")}
              >
                Reject
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {/* --- conversion --- */}
      {canDecide && status === "accepted" ? (
        <div>
          <div className="section-title" style={{ marginTop: 0 }}>
            Enrol
          </div>
          <p className="text-sm muted" style={{ margin: "0 0 8px" }}>
            Creates the student record and issues a student ID. This cannot be undone.
          </p>
          <button
            type="button"
            disabled={busy}
            onClick={() => void onAct(() => api.convertApplication(application.id), "Student record created.")}
          >
            Convert to student
          </button>
        </div>
      ) : null}

      {status === "enrolled" ? (
        <div className="alert alert--success">
          <span>Enrolled — a student record exists for this application.</span>
        </div>
      ) : null}
    </div>
  );
}
