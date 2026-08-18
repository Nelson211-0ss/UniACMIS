"use client";

/**
 * The offline queue, made visible.
 *
 * Users have to be able to see for themselves what has and has not reached the
 * server — otherwise "did that save?" gets answered by re-typing the form, which
 * is how duplicate records happen.
 */

import { useEffect, useState } from "react";

import { InboxIcon, RefreshIcon, SendIcon, TrashIcon } from "@/components/icons";
import * as outbox from "@/lib/outbox";
import { flush } from "@/lib/sync";

const STATUS_LABEL: Record<outbox.OutboxStatus, string> = {
  pending: "Pending",
  syncing: "Sending",
  failed: "Needs attention",
  synced: "Saved",
};

const STATUS_CLASS: Record<outbox.OutboxStatus, string> = {
  pending: "pill--pending",
  syncing: "pill--pending",
  failed: "pill--failed",
  synced: "pill--synced",
};

export default function OutboxPage() {
  const [operations, setOperations] = useState<outbox.OutboxOperation[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const refresh = () => void outbox.all().then(setOperations);
    refresh();
    return outbox.subscribe(refresh);
  }, []);

  async function sendNow() {
    setBusy(true);
    try {
      await flush(true);
      setOperations(await outbox.all());
    } finally {
      setBusy(false);
    }
  }

  async function clearSaved() {
    await outbox.clearSynced();
    setOperations(await outbox.all());
  }

  const unsent = operations.filter(
    (op) => op.status === "pending" || op.status === "failed",
  ).length;
  const savedCount = operations.filter((op) => op.status === "synced").length;

  return (
    <>
      <h1>Offline queue</h1>
      <p className="page-subtitle">
        Entries made on this device, and whether the server has them.
      </p>

      <div className="card">
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button type="button" onClick={sendNow} disabled={busy || unsent === 0}>
            {busy ? (
              <RefreshIcon size={16} className="spin" />
            ) : (
              <SendIcon size={16} />
            )}
            {busy ? "Sending…" : `Send ${unsent} queued`}
          </button>
          <button
            type="button"
            className="secondary"
            onClick={clearSaved}
            disabled={savedCount === 0}
          >
            <TrashIcon size={16} />
            Clear saved entries
          </button>
        </div>
        <p className="muted text-sm" style={{ marginTop: 12, marginBottom: 0 }}>
          Entries send automatically when a connection is available. Nothing is
          removed until the server confirms it, so closing the browser is safe.
        </p>
      </div>

      <div className="card">
        {operations.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__icon">
              <InboxIcon size={26} />
            </span>
            <span className="empty-state__title">Nothing queued on this device</span>
            <span className="text-sm">
              Entries made while offline will appear here until the server confirms
              them.
            </span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Entry</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Result</th>
                  <th>Tries</th>
                </tr>
              </thead>
              <tbody>
                {operations.map((op) => (
                  <tr key={op.clientOpId}>
                    <td>
                      <span className="cell-primary">{op.label || "(unnamed)"}</span>
                      <div className="text-sm muted">
                        {new Date(op.createdAt).toLocaleString()}
                      </div>
                    </td>
                    <td style={{ fontFamily: "var(--mono)", fontSize: "0.8125rem" }}>
                      {op.entity}
                    </td>
                    <td>
                      <span className={`pill ${STATUS_CLASS[op.status]}`}>
                        {STATUS_LABEL[op.status]}
                      </span>
                    </td>
                    <td className="text-sm">
                      {op.status === "synced" && op.result?.student_id ? (
                        <span style={{ fontFamily: "var(--mono)" }}>
                          {String(op.result.student_id)}
                        </span>
                      ) : (
                        op.lastError || "—"
                      )}
                    </td>
                    <td>{op.attempts}</td>
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
