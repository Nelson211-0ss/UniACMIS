"use client";

/** HR & leave (FR-HR-01…04). Any staff member requests their own leave; a
 * HOD endorses it; HR gives the final decision — three distinct actors,
 * matched here by three distinct actions rather than one generic "approve". */

import { useEffect, useState } from "react";

import { BriefcaseIcon } from "@/components/icons";
import { ApiFailure, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/** The export endpoint needs the same bearer token as everything else, so
 * a plain `<a href target="_blank">` (no Authorization header) would 401 —
 * fetch the rows with auth and build the CSV client-side instead. */
async function downloadPayrollCsv() {
  const rows = await api.payrollExport();
  if (rows.length === 0) return;
  const headers = Object.keys(rows[0]);
  const csv = [headers.join(","), ...rows.map((row) => headers.map((h) => String(row[h as keyof typeof row])).join(","))].join(
    "\n",
  );
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "payroll-export.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

interface LeaveRequest {
  id: number;
  staff: number;
  staff_number: string;
  leave_type: string;
  start_date: string;
  end_date: string;
  reason: string;
  status: string;
  decision_notes: string;
}

interface Appraisal {
  id: number;
  staff: number;
  staff_number: string;
  academic_year: number;
  rating: number;
  comments: string;
  promotion_recommended: boolean;
}

const STATUS_PILL: Record<string, string> = {
  submitted: "pill--pending",
  endorsed: "pill--info",
  approved: "pill--synced",
  rejected: "pill--failed",
};

export default function HrPage() {
  const { can, hasRole } = useAuth();
  const isHod = hasRole("hod");
  const isHr = can("hr.approve_leaverequest");
  const canExport = can("hr.export_payroll");

  const [leave, setLeave] = useState<LeaveRequest[]>([]);
  const [appraisals, setAppraisals] = useState<Appraisal[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "offline" | "error">("loading");
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const [leaveType, setLeaveType] = useState("annual");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [reason, setReason] = useState("");
  const [decisionFor, setDecisionFor] = useState<number | null>(null);
  const [decisionNotes, setDecisionNotes] = useState("");

  async function load() {
    try {
      const [leavePage, appraisalPage] = await Promise.all([
        api.leaveRequests(),
        api.appraisals().catch(() => ({ results: [] as Appraisal[] })),
      ]);
      setLeave(leavePage.results);
      setAppraisals(appraisalPage.results);
      setState("ready");
    } catch (error) {
      setState(error instanceof ApiFailure && error.offline ? "offline" : "error");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function submitLeave() {
    if (!startDate || !endDate || !reason.trim()) return;
    setBusy(true);
    setNotice(null);
    try {
      await api.submitLeaveRequest({ leave_type: leaveType, start_date: startDate, end_date: endDate, reason });
      setNotice({ kind: "success", text: "Leave request submitted." });
      setStartDate("");
      setEndDate("");
      setReason("");
      await load();
    } catch (error) {
      setNotice({
        kind: "error",
        text: error instanceof ApiFailure ? error.error.message : "Could not submit the request.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function endorse(id: number) {
    setBusy(true);
    try {
      await api.endorseLeaveRequest(id);
      await load();
    } catch (error) {
      setNotice({
        kind: "error",
        text: error instanceof ApiFailure ? error.error.message : "Could not endorse the request.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function decide(id: number, approve: boolean) {
    if (!decisionNotes.trim()) return;
    setBusy(true);
    try {
      await api.decideLeaveRequest(id, approve, decisionNotes);
      setDecisionFor(null);
      setDecisionNotes("");
      await load();
    } catch (error) {
      setNotice({
        kind: "error",
        text: error instanceof ApiFailure ? error.error.message : "Could not decide the request.",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>HR &amp; leave</h1>
          <p className="page-subtitle">Contracts, leave and appraisal</p>
        </div>
        {canExport ? (
          <button type="button" className="secondary" onClick={() => void downloadPayrollCsv()}>
            Payroll export
          </button>
        ) : null}
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

      <div className="grid">
        <div className="card">
          <div className="card__header">
            <span className="card__icon">
              <BriefcaseIcon size={18} />
            </span>
            <h2>Request leave</h2>
          </div>
          <div className="field">
            <label htmlFor="leave-type">Type</label>
            <select id="leave-type" value={leaveType} onChange={(event) => setLeaveType(event.target.value)}>
              {["annual", "sick", "maternity", "paternity", "study", "unpaid"].map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </div>
          <div className="field-row">
            <div className="field">
              <label htmlFor="leave-start">From</label>
              <input id="leave-start" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="leave-end">To</label>
              <input id="leave-end" type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
            </div>
          </div>
          <div className="field">
            <label htmlFor="leave-reason">Reason</label>
            <textarea id="leave-reason" rows={2} value={reason} onChange={(event) => setReason(event.target.value)} />
          </div>
          <button type="button" disabled={busy} onClick={() => void submitLeave()}>
            Submit request
          </button>
        </div>
      </div>

      <div className="section-title">Leave requests</div>
      <div className="card">
        {state !== "loading" && leave.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__title">No leave requests</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Staff</th>
                  <th>Type</th>
                  <th>Dates</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {leave.map((request) => (
                  <tr key={request.id}>
                    <td style={{ fontFamily: "var(--mono)" }}>{request.staff_number}</td>
                    <td>{request.leave_type}</td>
                    <td>
                      {request.start_date} → {request.end_date}
                    </td>
                    <td>
                      <span className={`pill ${STATUS_PILL[request.status] ?? ""}`}>{request.status}</span>
                    </td>
                    <td>
                      {isHod && request.status === "submitted" ? (
                        <button type="button" className="sm secondary" disabled={busy} onClick={() => void endorse(request.id)}>
                          Endorse
                        </button>
                      ) : null}
                      {isHr && request.status === "endorsed" ? (
                        decisionFor === request.id ? (
                          <div style={{ display: "flex", gap: 6 }}>
                            <input
                              value={decisionNotes}
                              onChange={(event) => setDecisionNotes(event.target.value)}
                              placeholder="Notes"
                              style={{ minWidth: 140 }}
                            />
                            <button type="button" className="sm" disabled={busy} onClick={() => void decide(request.id, true)}>
                              Approve
                            </button>
                            <button type="button" className="sm danger" disabled={busy} onClick={() => void decide(request.id, false)}>
                              Reject
                            </button>
                          </div>
                        ) : (
                          <button type="button" className="sm secondary" onClick={() => setDecisionFor(request.id)}>
                            Decide
                          </button>
                        )
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {appraisals.length > 0 ? (
        <>
          <div className="section-title">Appraisals</div>
          <div className="card">
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Staff</th>
                    <th>Rating</th>
                    <th>Comments</th>
                    <th>Promotion</th>
                  </tr>
                </thead>
                <tbody>
                  {appraisals.map((appraisal) => (
                    <tr key={appraisal.id}>
                      <td style={{ fontFamily: "var(--mono)" }}>{appraisal.staff_number}</td>
                      <td>{appraisal.rating}/5</td>
                      <td className="text-sm muted">{appraisal.comments || "—"}</td>
                      <td>{appraisal.promotion_recommended ? "Recommended" : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : null}
    </>
  );
}
