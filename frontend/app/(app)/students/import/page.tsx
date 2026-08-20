"use client";

/**
 * Bulk student import (NFR-DATA-03) — the browser-facing counterpart to the
 * `import_students` management command. Same all-or-nothing contract: a
 * dry run validates every row and reports what would happen, and nothing is
 * written until every row in the batch is valid.
 *
 * Not offline-capable — a spreadsheet upload has no natural place in the
 * outbox's single-entity model, so this is an online-only action like a
 * report export.
 */

import Link from "next/link";
import { useState } from "react";

import { AlertCircleIcon, CheckCircleIcon, UploadIcon } from "@/components/icons";
import { ApiFailure, api } from "@/lib/api";

interface RowError {
  row: number;
  errors: Record<string, string>;
}

interface ImportResult {
  total: number;
  valid: number;
  created: number;
  errors: RowError[];
}

const REQUIRED_COLUMNS = ["first_name", "last_name", "gender", "programme_code", "entry_academic_year"];
const OPTIONAL_COLUMNS = [
  "student_id",
  "middle_name",
  "date_of_birth (YYYY-MM-DD)",
  "national_id_number",
  "state_of_origin",
  "has_disability",
  "disability_details",
  "nationality",
  "phone",
  "email",
  "curriculum_version",
];

export default function BulkImportStudentsPage() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [committed, setCommitted] = useState(false);
  const [busy, setBusy] = useState<"validate" | "commit" | null>(null);
  const [error, setError] = useState("");

  function onFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
    setResult(null);
    setCommitted(false);
    setError("");
  }

  async function run(commit: boolean) {
    if (!file) return;
    setBusy(commit ? "commit" : "validate");
    setError("");
    try {
      const outcome = await api.bulkImportStudents(file, commit);
      setResult(outcome);
      setCommitted(commit && outcome.errors.length === 0);
    } catch (caught) {
      setError(
        caught instanceof ApiFailure
          ? caught.error.message
          : "Could not process the file. Try again shortly.",
      );
    } finally {
      setBusy(null);
    }
  }

  const canCommit = result !== null && result.errors.length === 0 && !committed;

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Bulk import students</h1>
          <p className="page-subtitle">Upload a CSV of legacy records — validate first, then commit.</p>
        </div>
        <Link href="/students" className="dashboard-section__link">
          ← Back to students
        </Link>
      </div>

      <div className="card">
        <div className="card__header">
          <span className="card__icon">
            <UploadIcon size={18} />
          </span>
          <h2>Choose a file</h2>
        </div>
        <div className="field">
          <label htmlFor="import-file">CSV file</label>
          <input id="import-file" type="file" accept=".csv,text/csv" onChange={onFileChange} />
          <div className="hint">
            Required columns: {REQUIRED_COLUMNS.join(", ")}. Optional: {OPTIONAL_COLUMNS.join(", ")}.
          </div>
        </div>

        {error ? (
          <div className="alert alert--error">
            <AlertCircleIcon size={18} />
            <span>{error}</span>
          </div>
        ) : null}

        <div className="form-actions">
          <button type="button" className="secondary" disabled={!file || busy !== null} onClick={() => void run(false)}>
            {busy === "validate" ? "Validating…" : "Validate"}
          </button>
          <button type="button" disabled={!canCommit || busy !== null} onClick={() => void run(true)}>
            {busy === "commit" ? "Importing…" : "Commit import"}
          </button>
        </div>
      </div>

      {result ? (
        <>
          <div className="grid">
            <div className="card stat stat--accent-blue">
              <span className="stat__label">Rows read</span>
              <div className="stat__value">{result.total}</div>
            </div>
            <div className="card stat stat--accent-teal">
              <span className="stat__label">Rows valid</span>
              <div className="stat__value">{result.valid}</div>
            </div>
            <div className={`card stat stat--accent-${result.created > 0 ? "teal" : "amber"}`}>
              <span className="stat__label">Students created</span>
              <div className="stat__value">{result.created}</div>
            </div>
            <div className={`card stat stat--accent-${result.errors.length > 0 ? "red" : "teal"}`}>
              <span className="stat__label">Rows rejected</span>
              <div className="stat__value">{result.errors.length}</div>
            </div>
          </div>

          {committed ? (
            <div className="alert alert--success">
              <CheckCircleIcon size={18} />
              <span>Created {result.created} student(s). The register now reflects this batch.</span>
            </div>
          ) : result.errors.length === 0 ? (
            <div className="alert alert--warning">
              <CheckCircleIcon size={18} />
              <span>Every row is valid — nothing has been written yet. Commit to create these students.</span>
            </div>
          ) : null}

          {result.errors.length > 0 ? (
            <>
              <div className="section-title">Rejected rows</div>
              <div className="card">
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Row</th>
                        <th>Field</th>
                        <th>Problem</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.errors.flatMap((entry) =>
                        Object.entries(entry.errors).map(([field, message]) => (
                          <tr key={`${entry.row}-${field}`}>
                            <td className="cell-primary">{entry.row}</td>
                            <td style={{ fontFamily: "var(--mono)" }}>{field}</td>
                            <td>{message}</td>
                          </tr>
                        )),
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          ) : null}
        </>
      ) : null}
    </>
  );
}
