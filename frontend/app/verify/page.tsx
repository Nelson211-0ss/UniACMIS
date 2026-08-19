"use client";

/** Public document verification (FR-DOC-03) — no login, reached by scanning
 * the QR code or typing the serial off a printed transcript or certificate. */

import { useState } from "react";

import { AlertCircleIcon, CheckCircleIcon, FileTextIcon, GraduationCapIcon } from "@/components/icons";
import { api } from "@/lib/api";

type Result =
  | { serial_number: string; document_type: string; student_name: string; issued_at: string; is_valid: boolean }
  | "not_found"
  | null;

export default function VerifyPage() {
  const [serial, setSerial] = useState("");
  const [result, setResult] = useState<Result>(null);
  const [checking, setChecking] = useState(false);

  async function verify() {
    if (!serial.trim()) return;
    setChecking(true);
    setResult(null);
    try {
      setResult(await api.verifyDocument(serial.trim()));
    } catch {
      setResult("not_found");
    } finally {
      setChecking(false);
    }
  }

  return (
    <main className="splash">
      <div className="splash__card" style={{ maxWidth: 440 }}>
        <span className="splash__brand">
          <GraduationCapIcon size={26} />
        </span>
        <h1 className="login__title">Verify a document</h1>
        <p className="login__sub">
          Enter the serial number printed on a UniACMIS transcript or certificate to confirm it is
          genuine.
        </p>

        <div className="field" style={{ textAlign: "left" }}>
          <label htmlFor="serial">Serial number</label>
          <input
            id="serial"
            value={serial}
            onChange={(event) => setSerial(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && void verify()}
            placeholder="e.g. CERT/2026/00001"
          />
        </div>
        <button type="button" disabled={checking} onClick={() => void verify()} style={{ width: "100%" }}>
          {checking ? "Checking…" : "Verify"}
        </button>

        {result === "not_found" ? (
          <div className="alert alert--error" style={{ marginTop: 16, textAlign: "left" }}>
            <AlertCircleIcon size={18} />
            <span>No document exists with this serial number.</span>
          </div>
        ) : null}

        {result && result !== "not_found" ? (
          <div
            className={`alert alert--${result.is_valid ? "success" : "error"}`}
            style={{ marginTop: 16, textAlign: "left" }}
          >
            {result.is_valid ? <CheckCircleIcon size={18} /> : <AlertCircleIcon size={18} />}
            <div>
              <strong>{result.is_valid ? "Genuine document" : "This document has been revoked"}</strong>
              <div className="text-sm" style={{ marginTop: 4 }}>
                <FileTextIcon size={14} style={{ display: "inline", marginRight: 4, verticalAlign: "-2px" }} />
                {result.document_type} issued to {result.student_name} on{" "}
                {new Date(result.issued_at).toLocaleDateString()}
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </main>
  );
}
