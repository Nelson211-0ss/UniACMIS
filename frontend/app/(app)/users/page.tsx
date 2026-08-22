"use client";

/**
 * Staff accounts and role assignment (NFR-SEC-01).
 *
 * A new account always starts with `must_change_password` set server-side —
 * whoever typed the initial password necessarily knows it, so it cannot be the
 * one the holder keeps. Role grants and revocations are themselves audited, and
 * a revoked grant is kept rather than deleted, so "who could do what, when" is
 * answerable after the fact; the history panel is that record.
 */

import { useEffect, useState } from "react";

import { UserPlusIcon, UsersIcon } from "@/components/icons";
import { ApiFailure, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface ManagedUser {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  phone: string;
  is_active: boolean;
  mfa_enabled: boolean;
  must_change_password: boolean;
  roles: string[];
  last_login: string | null;
}

interface RoleOption {
  code: string;
  name: string;
  description: string;
}

function errorText(error: unknown, fallback: string) {
  return error instanceof ApiFailure ? error.error.message : fallback;
}

export default function UsersPage() {
  const { can } = useAuth();
  const canAdd = can("accounts.add_user");
  const canChange = can("accounts.change_user");
  const canGrant = can("accounts.add_userrole");
  const canRevoke = can("accounts.change_userrole");

  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [roles, setRoles] = useState<RoleOption[]>([]);
  const [search, setSearch] = useState("");
  const [state, setState] = useState<"loading" | "ready" | "offline" | "error">("loading");
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const [email, setEmail] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");

  const [roleFor, setRoleFor] = useState<number | null>(null);
  const [roleCode, setRoleCode] = useState("");
  const [roleReason, setRoleReason] = useState("");
  const [history, setHistory] = useState<{
    userId: number;
    rows: Array<{
      id: number;
      role_code: string;
      granted_at: string;
      granted_by_name: string;
      revoked_at: string | null;
      reason: string;
    }>;
  } | null>(null);

  async function load() {
    try {
      const params = search.trim() ? `?page_size=100&search=${encodeURIComponent(search.trim())}` : "?page_size=100";
      const [userPage, rolePage] = await Promise.all([
        api.users(params),
        // The role list is reference data — fetched once alongside, and a
        // failure here should not blank out the user list itself.
        api.roles().catch(() => [] as RoleOption[]),
      ]);
      setUsers(userPage.results);
      setRoles(rolePage);
      setState("ready");
    } catch (error) {
      setState(error instanceof ApiFailure && error.offline ? "offline" : "error");
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function createUser() {
    if (!email.trim() || !firstName.trim() || !lastName.trim() || password.length < 8) {
      setNotice({ kind: "error", text: "Email, both names and a password of at least 8 characters are required." });
      return;
    }
    setBusy(true);
    setNotice(null);
    try {
      await api.createUser({
        email: email.trim(),
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        phone: phone.trim(),
        password,
      });
      setNotice({
        kind: "success",
        text: "Account created. The holder must change this password at first sign-in.",
      });
      setEmail("");
      setFirstName("");
      setLastName("");
      setPhone("");
      setPassword("");
      await load();
    } catch (error) {
      setNotice({ kind: "error", text: errorText(error, "Could not create the account.") });
    } finally {
      setBusy(false);
    }
  }

  async function toggleActive(user: ManagedUser) {
    setBusy(true);
    try {
      await api.updateUser(user.id, { is_active: !user.is_active });
      setNotice({
        kind: "success",
        text: `${user.full_name} ${user.is_active ? "deactivated" : "reactivated"}.`,
      });
      await load();
    } catch (error) {
      setNotice({ kind: "error", text: errorText(error, "Could not update the account.") });
    } finally {
      setBusy(false);
    }
  }

  async function forcePasswordChange(user: ManagedUser) {
    setBusy(true);
    try {
      await api.updateUser(user.id, { must_change_password: true });
      setNotice({ kind: "success", text: `${user.full_name} must change their password at next sign-in.` });
      await load();
    } catch (error) {
      setNotice({ kind: "error", text: errorText(error, "Could not flag the account.") });
    } finally {
      setBusy(false);
    }
  }

  async function grant(userId: number) {
    if (!roleCode) return;
    setBusy(true);
    try {
      await api.grantRole(userId, roleCode, roleReason || "Granted via user administration");
      setNotice({ kind: "success", text: `Granted ${roleCode}.` });
      setRoleFor(null);
      setRoleCode("");
      setRoleReason("");
      await load();
    } catch (error) {
      setNotice({ kind: "error", text: errorText(error, "Could not grant that role.") });
    } finally {
      setBusy(false);
    }
  }

  async function revoke(userId: number, code: string) {
    setBusy(true);
    try {
      await api.revokeRole(userId, code, "Revoked via user administration");
      setNotice({ kind: "success", text: `Revoked ${code}.` });
      await load();
    } catch (error) {
      setNotice({ kind: "error", text: errorText(error, "Could not revoke that role.") });
    } finally {
      setBusy(false);
    }
  }

  async function showHistory(userId: number) {
    if (history?.userId === userId) {
      setHistory(null);
      return;
    }
    try {
      const rows = await api.roleHistory(userId);
      setHistory({ userId, rows });
    } catch (error) {
      setNotice({ kind: "error", text: errorText(error, "Could not load the role history.") });
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Users &amp; roles</h1>
          <p className="page-subtitle">Staff accounts and what each of them may do</p>
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
          <span>Could not load accounts. Try again shortly.</span>
        </div>
      ) : null}

      {canAdd ? (
        <div className="card">
          <div className="card__header">
            <span className="card__icon">
              <UserPlusIcon size={18} />
            </span>
            <h2>Create a staff account</h2>
          </div>
          <div className="field-row">
            <div className="field" style={{ flex: 2 }}>
              <label htmlFor="u-email">Email</label>
              <input id="u-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="u-first">First name</label>
              <input id="u-first" value={firstName} onChange={(event) => setFirstName(event.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="u-last">Last name</label>
              <input id="u-last" value={lastName} onChange={(event) => setLastName(event.target.value)} />
            </div>
          </div>
          <div className="field-row">
            <div className="field">
              <label htmlFor="u-phone">Phone</label>
              <input id="u-phone" value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="+211…" />
            </div>
            <div className="field">
              <label htmlFor="u-password">Initial password</label>
              <input
                id="u-password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="At least 8 characters"
              />
            </div>
          </div>
          <p className="text-sm muted" style={{ margin: "0 0 12px" }}>
            The holder is required to change this at first sign-in. Assign a role after creating the account.
          </p>
          <button type="button" disabled={busy} onClick={() => void createUser()}>
            Create account
          </button>
        </div>
      ) : null}

      <div className="card">
        <div className="field">
          <label htmlFor="u-search">Search</label>
          <input
            id="u-search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void load();
            }}
            placeholder="Name, email or phone"
          />
        </div>
        <button type="button" className="secondary" onClick={() => void load()}>
          Search
        </button>
      </div>

      <div className="section-title">Accounts</div>
      <div className="card">
        {state === "loading" ? (
          <p className="muted">Loading…</p>
        ) : users.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__title">No accounts match</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Roles</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id}>
                    <td className="cell-primary">
                      {user.full_name}
                      {user.must_change_password ? (
                        <div>
                          <span className="pill pill--pending">Password change due</span>
                        </div>
                      ) : null}
                    </td>
                    <td className="text-sm">{user.email}</td>
                    <td>
                      {user.roles.length === 0 ? (
                        <span className="muted text-sm">None</span>
                      ) : (
                        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                          {user.roles.map((code) => (
                            <span key={code} className="pill pill--info" style={{ display: "inline-flex", gap: 4 }}>
                              {code}
                              {canRevoke ? (
                                <button
                                  type="button"
                                  className="sm ghost"
                                  style={{ padding: "0 4px", minHeight: 0 }}
                                  disabled={busy}
                                  onClick={() => void revoke(user.id, code)}
                                  aria-label={`Revoke ${code}`}
                                >
                                  ×
                                </button>
                              ) : null}
                            </span>
                          ))}
                        </div>
                      )}
                      {roleFor === user.id ? (
                        <div style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "wrap" }}>
                          <select value={roleCode} onChange={(event) => setRoleCode(event.target.value)}>
                            <option value="">Select a role…</option>
                            {roles
                              .filter((role) => !user.roles.includes(role.code))
                              .map((role) => (
                                <option key={role.code} value={role.code}>
                                  {role.name}
                                </option>
                              ))}
                          </select>
                          <input
                            value={roleReason}
                            onChange={(event) => setRoleReason(event.target.value)}
                            placeholder="Reason"
                            style={{ minWidth: 120 }}
                          />
                          <button type="button" className="sm" disabled={busy || !roleCode} onClick={() => void grant(user.id)}>
                            Grant
                          </button>
                        </div>
                      ) : null}
                    </td>
                    <td>
                      <span className={`pill ${user.is_active ? "pill--synced" : "pill--failed"}`}>
                        {user.is_active ? "Active" : "Inactive"}
                      </span>
                      {user.mfa_enabled ? (
                        <div>
                          <span className="pill pill--info">MFA</span>
                        </div>
                      ) : null}
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        {canGrant ? (
                          <button
                            type="button"
                            className="sm secondary"
                            onClick={() => setRoleFor(roleFor === user.id ? null : user.id)}
                          >
                            {roleFor === user.id ? "Cancel" : "Add role"}
                          </button>
                        ) : null}
                        {canChange ? (
                          <>
                            <button type="button" className="sm ghost" disabled={busy} onClick={() => void toggleActive(user)}>
                              {user.is_active ? "Deactivate" : "Reactivate"}
                            </button>
                            {!user.must_change_password ? (
                              <button
                                type="button"
                                className="sm ghost"
                                disabled={busy}
                                onClick={() => void forcePasswordChange(user)}
                              >
                                Force reset
                              </button>
                            ) : null}
                          </>
                        ) : null}
                        <button type="button" className="sm ghost" onClick={() => void showHistory(user.id)}>
                          {history?.userId === user.id ? "Hide history" : "History"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {history ? (
        <div className="card">
          <div className="card__header">
            <span className="card__icon">
              <UsersIcon size={18} />
            </span>
            <h2>Role history</h2>
          </div>
          {history.rows.length === 0 ? (
            <p className="muted">No role grants recorded for this account.</p>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Role</th>
                    <th>Granted</th>
                    <th>By</th>
                    <th>Revoked</th>
                    <th>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {history.rows.map((row) => (
                    <tr key={row.id}>
                      <td className="cell-primary">{row.role_code}</td>
                      <td className="text-sm">{new Date(row.granted_at).toLocaleString()}</td>
                      <td className="text-sm">{row.granted_by_name || "—"}</td>
                      <td className="text-sm">
                        {row.revoked_at ? new Date(row.revoked_at).toLocaleString() : "—"}
                      </td>
                      <td className="text-sm muted">{row.reason || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : null}
    </>
  );
}
