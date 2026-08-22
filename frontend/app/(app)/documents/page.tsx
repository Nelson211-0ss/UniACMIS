"use client";

/** Documents & certification (FR-DOC-01…04). A student requests their own
 * transcript and sees their own issued documents; the registrar decides
 * requests and issues certificates, gated by graduation clearance. */

import { useEffect, useState } from "react";

import { FileTextIcon } from "@/components/icons";
import { ApiFailure, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface TranscriptRequest {
  id: number;
  student: number;
  student_number: string;
  reason: string;
  status: string;
  decision_notes: string;
}

interface IssuedDocument {
  id: number;
  student: number;
  student_number: string;
  document_type: string;
  serial_number: string;
  issued_at: string;
  is_revoked: boolean;
}

const STATUS_PILL: Record<string, string> = {
  requested: "pill--pending",
  issued: "pill--synced",
  rejected: "pill--failed",
};

export default function DocumentsPage() {
  const { can } = useAuth();
  const canDecide = can("documents.change_transcriptrequest");
  const canIssue = can("documents.issue_certificate");
  const canRevoke = can("documents.revoke_document");

  const [requests, setRequests] = useState<TranscriptRequest[]>([]);
  const [issued, setIssued] = useState<IssuedDocument[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "offline" | "error">("loading");
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const [reason, setReason] = useState("");
  const [decisionFor, setDecisionFor] = useState<number | null>(null);
  const [decisionNotes, setDecisionNotes] = useState("");
  const [issueStudent, setIssueStudent] = useState("");
  const [verifySerial, setVerifySerial] = useState("");
  const [verifyResult, setVerifyResult] = useState<
    { serial_number: string; document_type: string; student_name: string; is_valid: boolean } | null | "not_found"
  >(null);

  async function load() {
    try {
      const [requestPage, issuedPage] = await Promise.all([
        api.transcriptRequests(),
        api.issuedDocuments().catch(() => ({ results: [] as IssuedDocument[] })),
      ]);
      setRequests(requestPage.results);
      setIssued(issuedPage.results);
      setState("ready");
    } catch (error) {
      setState(error instanceof ApiFailure && error.offline ? "offline" : "error");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function submitRequest() {
    setBusy(true);
    setNotice(null);
    try {
      await api.requestTranscript(reason);
      setNotice({ kind: "success", text: "Transcript requested." });
      setReason("");
      await load();
    } catch (error) {
      setNotice({ kind: "error", text: error instanceof ApiFailure ? error.error.message : "Could not submit the request." });
    } finally {
      setBusy(false);
    }
  }

  async function decide(id: number, approve: boolean) {
    if (!decisionNotes.trim()) return;
    setBusy(true);
    try {
      await api.decideTranscriptRequest(id, approve, decisionNotes);
      setDecisionFor(null);
      setDecisionNotes("");
      await load();
    } catch (error) {
      setNotice({ kind: "error", text: error instanceof ApiFailure ? error.error.message : "Could not decide the request." });
    } finally {
      setBusy(false);
    }
  }

  async function issueCertificate() {
    if (!issueStudent) return;
    setBusy(true);
    setNotice(null);
    try {
      const result = await api.issueCertificate(Number(issueStudent));
      setNotice({ kind: "success", text: `Certificate issued: ${result.serial_number}` });
      setIssueStudent("");
      await load();
    } catch (error) {
      setNotice({
        kind: "error",
        text: error instanceof ApiFailure ? error.error.message : "Could not issue the certificate — check for an open clearance hold.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function revoke(id: number) {
    setBusy(true);
    try {
      await api.revokeDocument(id, "Revoked from the documents page");
      await load();
    } catch (error) {
      setNotice({ kind: "error", text: error instanceof ApiFailure ? error.error.message : "Could not revoke this document." });
    } finally {
      setBusy(false);
    }
  }

  async function verify() {
    if (!verifySerial.trim()) return;
    try {
      setVerifyResult(await api.verifyDocument(verifySerial.trim()));
    } catch {
      setVerifyResult("not_found");
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Documents</h1>
          <p className="page-subtitle">Transcripts and certificates</p>
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
          <span>Could not load your documents. Try again shortly.</span>
        </div>
      ) : null}

      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))" }}>
        <div className="card">
          <div className="card__header">
            <span className="card__icon">
              <FileTextIcon size={18} />
            </span>
            <h2>Request a transcript</h2>
          </div>
          <div className="field">
            <label htmlFor="reason">Reason</label>
            <input id="reason" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="e.g. Job application" />
          </div>
          <button type="button" disabled={busy} onClick={() => void submitRequest()}>
            Submit request
          </button>
        </div>

        {canIssue ? (
          <div className="card">
            <div className="card__header">
              <h2>Issue a certificate</h2>
            </div>
            <div className="field">
              <label htmlFor="issue-student">Student ID</label>
              <input id="issue-student" value={issueStudent} onChange={(event) => setIssueStudent(event.target.value)} />
            </div>
            <button type="button" disabled={busy} onClick={() => void issueCertificate()}>
              Issue certificate
            </button>
          </div>
        ) : null}

        <div className="card">
          <div className="card__header">
            <h2>Verify a document</h2>
          </div>
          <div className="field">
            <label htmlFor="verify-serial">Serial number</label>
            <input id="verify-serial" value={verifySerial} onChange={(event) => setVerifySerial(event.target.value)} placeholder="e.g. CERT/2026/00001" />
          </div>
          <button type="button" className="secondary" onClick={() => void verify()}>
            Verify
          </button>
          {verifyResult === "not_found" ? <p className="text-sm" style={{ color: "var(--status-hold)" }}>No document with this serial number.</p> : null}
          {verifyResult && verifyResult !== "not_found" ? (
            <p className="text-sm" style={{ marginTop: 8 }}>
              <span className={`pill ${verifyResult.is_valid ? "pill--synced" : "pill--failed"}`}>
                {verifyResult.is_valid ? "Valid" : "Revoked"}
              </span>{" "}
              {verifyResult.document_type} for {verifyResult.student_name}
            </p>
          ) : null}
        </div>
      </div>

      <div className="section-title">Transcript requests</div>
      <div className="card">
        {state !== "loading" && requests.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__title">No requests</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Student</th>
                  <th>Reason</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {requests.map((request) => (
                  <tr key={request.id}>
                    <td style={{ fontFamily: "var(--mono)" }}>{request.student_number}</td>
                    <td className="text-sm muted">{request.reason || "—"}</td>
                    <td>
                      <span className={`pill ${STATUS_PILL[request.status] ?? ""}`}>{request.status}</span>
                    </td>
                    <td>
                      {canDecide && request.status === "requested" ? (
                        decisionFor === request.id ? (
                          <div style={{ display: "flex", gap: 6 }}>
                            <input value={decisionNotes} onChange={(event) => setDecisionNotes(event.target.value)} placeholder="Notes" style={{ width: 120 }} />
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

      <div className="section-title">Issued documents</div>
      <div className="card">
        {state !== "loading" && issued.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__title">Nothing issued yet</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Serial</th>
                  <th>Student</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {issued.map((document) => (
                  <tr key={document.id}>
                    <td style={{ fontFamily: "var(--mono)" }}>{document.serial_number}</td>
                    <td style={{ fontFamily: "var(--mono)" }}>{document.student_number}</td>
                    <td>{document.document_type}</td>
                    <td>
                      <span className={`pill ${document.is_revoked ? "pill--failed" : "pill--synced"}`}>
                        {document.is_revoked ? "Revoked" : "Valid"}
                      </span>
                    </td>
                    <td>
                      {canRevoke && !document.is_revoked ? (
                        <button type="button" className="sm ghost" disabled={busy} onClick={() => void revoke(document.id)}>
                          Revoke
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
