"use client";

/**
 * Audit trail viewer (FR-RPT-04, NFR-SEC-03).
 *
 * Read-only by construction, not by omission: `AuditLog` refuses `save()` on an
 * existing row and `delete()` outright, and the API exposes no write route at
 * all. So there is deliberately no "edit" or "remove" affordance anywhere here —
 * the whole value of the trail is that nobody, including whoever is looking at
 * this page, can alter it.
 *
 * Paginated by cursor rather than page number (an append-only table has no
 * stable total to count), so navigation is next/previous only.
 */

import { useEffect, useState } from "react";

import { AlertCircleIcon, CheckCircleIcon, FingerprintIcon } from "@/components/icons";
import { ApiFailure, api } from "@/lib/api";

interface Entry {
  id: number;
  entity: string;
  object_id: string;
  object_repr: string;
  action: string;
  field_name: string;
  old_value: string | null;
  new_value: string | null;
  description: string;
  reason: string;
  actor_display: string;
  actor_role: string;
  ip_address: string | null;
  request_id: string;
  created_at: string;
}

const ACTIONS = [
  "create",
  "update",
  "delete",
  "login",
  "logout",
  "login_failed",
  "view_sensitive",
  "approve",
  "reject",
  "role_grant",
  "role_revoke",
  "sync_overwrite",
  "export",
  "mfa_enabled",
  "mfa_disabled",
];

const ACTION_PILL: Record<string, string> = {
  create: "pill--synced",
  update: "pill--info",
  delete: "pill--failed",
  login_failed: "pill--failed",
  approve: "pill--synced",
  reject: "pill--failed",
  role_grant: "pill--info",
  role_revoke: "pill--pending",
  view_sensitive: "pill--pending",
};

export default function AuditPage() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [prevCursor, setPrevCursor] = useState<string | null>(null);
  const [action, setAction] = useState("");
  const [entity, setEntity] = useState("");
  const [search, setSearch] = useState("");
  const [state, setState] = useState<"loading" | "ready" | "offline" | "error">("loading");
  const [chain, setChain] = useState<{ ok: boolean; checked: number; detail: string } | null>(null);
  const [verifying, setVerifying] = useState(false);

  async function load(url?: string) {
    setState("loading");
    try {
      // A cursor URL from a previous page already carries its own query string;
      // building a fresh one would drop the cursor and silently restart.
      let params = url ? url.slice(url.indexOf("?")) : "?page_size=50";
      if (!url) {
        if (action) params += `&action=${action}`;
        if (entity.trim()) params += `&entity=${encodeURIComponent(entity.trim())}`;
        if (search.trim()) params += `&search=${encodeURIComponent(search.trim())}`;
      }
      const page = await api.auditEntries(params);
      setEntries(page.results);
      setNextCursor(page.next);
      setPrevCursor(page.previous);
      setState("ready");
    } catch (error) {
      setState(error instanceof ApiFailure && error.offline ? "offline" : "error");
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function verify() {
    setVerifying(true);
    try {
      const result = await api.verifyAuditChain();
      setChain(result);
    } catch {
      setChain({ ok: false, checked: 0, detail: "Could not verify the chain." });
    } finally {
      setVerifying(false);
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Audit trail</h1>
          <p className="page-subtitle">Every change, hash-chained and append-only</p>
        </div>
        <button type="button" className="secondary" disabled={verifying} onClick={() => void verify()}>
          {verifying ? "Verifying…" : "Verify chain integrity"}
        </button>
      </div>

      {chain ? (
        <div className={`alert alert--${chain.ok ? "success" : "error"}`}>
          {chain.ok ? <CheckCircleIcon size={16} /> : <AlertCircleIcon size={16} />}
          <span>
            {chain.detail} {chain.checked > 0 ? `(${chain.checked} entries checked)` : null}
          </span>
        </div>
      ) : null}
      {state === "offline" ? (
        <div className="alert alert--warning">
          <span>No connection. Showing whatever loaded earlier on this device.</span>
        </div>
      ) : null}
      {state === "error" ? (
        <div className="alert alert--error">
          <span>Could not load the audit trail. Try again shortly.</span>
        </div>
      ) : null}

      <div className="card">
        <div className="card__header">
          <span className="card__icon">
            <FingerprintIcon size={18} />
          </span>
          <h2>Filter</h2>
        </div>
        <div className="field-row">
          <div className="field">
            <label htmlFor="audit-action">Action</label>
            <select id="audit-action" value={action} onChange={(event) => setAction(event.target.value)}>
              <option value="">Any</option>
              {ACTIONS.map((value) => (
                <option key={value} value={value}>
                  {value.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="audit-entity">Entity</label>
            <input
              id="audit-entity"
              value={entity}
              onChange={(event) => setEntity(event.target.value)}
              placeholder="registry.student"
            />
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label htmlFor="audit-search">Search</label>
            <input
              id="audit-search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Record, field, actor or reason"
            />
          </div>
        </div>
        <button type="button" onClick={() => void load()}>
          Apply
        </button>
      </div>

      <div className="card">
        {state === "loading" ? (
          <p className="muted">Loading…</p>
        ) : entries.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__title">No entries match</span>
            <p className="muted">Try a wider filter.</p>
          </div>
        ) : (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Action</th>
                    <th>Record</th>
                    <th>Change</th>
                    <th>Actor</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((entry) => (
                    <tr key={entry.id}>
                      <td className="text-sm" style={{ whiteSpace: "nowrap" }}>
                        {new Date(entry.created_at).toLocaleString()}
                      </td>
                      <td>
                        <span className={`pill ${ACTION_PILL[entry.action] ?? ""}`}>
                          {entry.action.replace(/_/g, " ")}
                        </span>
                      </td>
                      <td>
                        <div className="cell-primary">{entry.object_repr || "—"}</div>
                        <div className="text-sm muted" style={{ fontFamily: "var(--mono)" }}>
                          {entry.entity}
                          {entry.object_id ? `#${entry.object_id}` : ""}
                        </div>
                      </td>
                      <td className="text-sm">
                        {entry.field_name ? (
                          <>
                            <span className="muted">{entry.field_name}: </span>
                            <s className="muted">{entry.old_value ?? "—"}</s> → {entry.new_value ?? "—"}
                          </>
                        ) : (
                          entry.description || "—"
                        )}
                        {entry.reason ? (
                          <div className="muted" style={{ marginTop: 2 }}>
                            {entry.reason}
                          </div>
                        ) : null}
                      </td>
                      <td className="text-sm">
                        {entry.actor_display}
                        {entry.actor_role ? (
                          <div className="muted">{entry.actor_role}</div>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <button
                type="button"
                className="secondary sm"
                disabled={!prevCursor}
                onClick={() => void load(prevCursor ?? undefined)}
              >
                ← Newer
              </button>
              <button
                type="button"
                className="secondary sm"
                disabled={!nextCursor}
                onClick={() => void load(nextCursor ?? undefined)}
              >
                Older →
              </button>
            </div>
          </>
        )}
      </div>
    </>
  );
}
