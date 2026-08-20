"use client";

/** Communications (FR-COM-01…03). Announcements are open to read by
 * whoever is in their audience; sending is a registrar/HOD action. */

import { useEffect, useState } from "react";

import { MegaphoneIcon } from "@/components/icons";
import { ApiFailure, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Announcement {
  id: number;
  title: string;
  body: string;
  audience_type: string;
  sent_at: string;
  recipient_count: number;
}

const AUDIENCE_LABEL: Record<string, string> = {
  all_students: "All students",
  programme: "One programme",
  alumni: "Alumni",
};

export default function CommunicationsPage() {
  const { can } = useAuth();
  const canSend = can("communications.send_announcement");
  const canBroadcast = can("communications.broadcast_all");

  const [announcements, setAnnouncements] = useState<Announcement[]>([]);
  const [programmes, setProgrammes] = useState<Array<{ id: number; code: string; name: string }>>([]);
  const [state, setState] = useState<"loading" | "ready" | "offline" | "error">("loading");
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [audience, setAudience] = useState("programme");
  const [programme, setProgramme] = useState("");

  async function load() {
    try {
      const page = await api.announcements();
      setAnnouncements(page.results);
      if (canSend) {
        setProgrammes((await api.programmes().catch(() => ({ results: [] }))).results);
      }
      setState("ready");
    } catch (error) {
      setState(error instanceof ApiFailure && error.offline ? "offline" : "error");
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function send() {
    if (!title.trim() || !body.trim()) return;
    if (audience === "programme" && !programme) return;
    setBusy(true);
    setNotice(null);
    try {
      await api.sendAnnouncement({
        title,
        body,
        audience_type: audience,
        ...(audience === "programme" ? { programme: Number(programme) } : {}),
      });
      setNotice({ kind: "success", text: "Announcement sent." });
      setTitle("");
      setBody("");
      await load();
    } catch (error) {
      setNotice({ kind: "error", text: error instanceof ApiFailure ? error.error.message : "Could not send the announcement." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Announcements</h1>
          <p className="page-subtitle">Notices for your audience</p>
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

      {canSend ? (
        <div className="card">
          <div className="card__header">
            <span className="card__icon">
              <MegaphoneIcon size={18} />
            </span>
            <h2>Send an announcement</h2>
          </div>
          <div className="field">
            <label htmlFor="ann-title">Title</label>
            <input id="ann-title" value={title} onChange={(event) => setTitle(event.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="ann-body">Message</label>
            <textarea id="ann-body" rows={3} value={body} onChange={(event) => setBody(event.target.value)} />
          </div>
          <div className="field-row">
            <div className="field">
              <label htmlFor="ann-audience">Audience</label>
              <select id="ann-audience" value={audience} onChange={(event) => setAudience(event.target.value)}>
                <option value="programme">One programme</option>
                {canBroadcast ? <option value="all_students">All students</option> : null}
                {canBroadcast ? <option value="alumni">Alumni</option> : null}
              </select>
            </div>
            {audience === "programme" ? (
              <div className="field">
                <label htmlFor="ann-programme">Programme</label>
                <select id="ann-programme" value={programme} onChange={(event) => setProgramme(event.target.value)}>
                  <option value="">Select a programme</option>
                  {programmes.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.code} — {p.name}
                    </option>
                  ))}
                </select>
              </div>
            ) : null}
          </div>
          <button type="button" disabled={busy} onClick={() => void send()}>
            Send
          </button>
        </div>
      ) : null}

      <div className="card">
        {state !== "loading" && announcements.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__icon">
              <MegaphoneIcon size={26} />
            </span>
            <span className="empty-state__title">No announcements yet</span>
          </div>
        ) : (
          <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 16 }}>
            {announcements.map((announcement) => (
              <li key={announcement.id} style={{ paddingBottom: 16, borderBottom: "1px solid var(--border)" }}>
                <div className="row-flex" style={{ justifyContent: "space-between" }}>
                  <strong>{announcement.title}</strong>
                  <span className="pill">{AUDIENCE_LABEL[announcement.audience_type] ?? announcement.audience_type}</span>
                </div>
                <p className="text-sm muted" style={{ margin: "6px 0" }}>
                  {announcement.body}
                </p>
                <span className="text-sm muted">
                  {new Date(announcement.sent_at).toLocaleDateString()} · {announcement.recipient_count} recipient(s)
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}
