"use client";

/** Alumni (FR-ALM-01…02). Registrar-managed — tracer profiles and events. */

import { useEffect, useState } from "react";

import { UserGraduateIcon } from "@/components/icons";
import { ApiFailure, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface AlumniProfile {
  id: number;
  student_number: string;
  student_name: string;
  current_employer: string;
  employment_status: string;
  is_contactable: boolean;
}

interface AlumniEvent {
  id: number;
  title: string;
  event_date: string;
  location: string;
}

export default function AlumniPage() {
  const { can } = useAuth();
  const canManageProfiles = can("alumni.add_alumniprofile");
  const canManageEvents = can("alumni.add_alumnievent");

  const [profiles, setProfiles] = useState<AlumniProfile[]>([]);
  const [events, setEvents] = useState<AlumniEvent[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "offline" | "error">("loading");
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const [newStudent, setNewStudent] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [newDate, setNewDate] = useState("");
  const [newLocation, setNewLocation] = useState("");

  async function load() {
    try {
      const [profilePage, eventPage] = await Promise.all([api.alumniProfiles(), api.alumniEvents()]);
      setProfiles(profilePage.results);
      setEvents(eventPage.results);
      setState("ready");
    } catch (error) {
      setState(error instanceof ApiFailure && error.offline ? "offline" : "error");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function addProfile() {
    if (!newStudent) return;
    setBusy(true);
    setNotice(null);
    try {
      await api.createAlumniProfile({ student: Number(newStudent) });
      setNotice({ kind: "success", text: "Alumni profile created." });
      setNewStudent("");
      await load();
    } catch (error) {
      setNotice({
        kind: "error",
        text: error instanceof ApiFailure ? error.error.message : "Could not create the profile — the student must be graduated.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function addEvent() {
    if (!newTitle.trim() || !newDate) return;
    setBusy(true);
    setNotice(null);
    try {
      await api.createAlumniEvent({ title: newTitle, event_date: newDate, location: newLocation });
      setNotice({ kind: "success", text: "Event scheduled." });
      setNewTitle("");
      setNewDate("");
      setNewLocation("");
      await load();
    } catch (error) {
      setNotice({ kind: "error", text: error instanceof ApiFailure ? error.error.message : "Could not schedule the event." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Alumni</h1>
          <p className="page-subtitle">Tracer profiles and events</p>
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
          <span>Could not load alumni records. Try again shortly.</span>
        </div>
      ) : null}

      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))" }}>
        {canManageProfiles ? (
          <div className="card">
            <div className="card__header">
              <span className="card__icon">
                <UserGraduateIcon size={18} />
              </span>
              <h2>Create an alumni profile</h2>
            </div>
            <div className="field">
              <label htmlFor="new-student">Graduated student ID</label>
              <input id="new-student" value={newStudent} onChange={(event) => setNewStudent(event.target.value)} />
            </div>
            <button type="button" disabled={busy} onClick={() => void addProfile()}>
              Create profile
            </button>
          </div>
        ) : null}

        {canManageEvents ? (
          <div className="card">
            <div className="card__header">
              <h2>Schedule an event</h2>
            </div>
            <div className="field">
              <label htmlFor="event-title">Title</label>
              <input id="event-title" value={newTitle} onChange={(event) => setNewTitle(event.target.value)} />
            </div>
            <div className="field-row">
              <div className="field">
                <label htmlFor="event-date">Date</label>
                <input id="event-date" type="date" value={newDate} onChange={(event) => setNewDate(event.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="event-location">Location</label>
                <input id="event-location" value={newLocation} onChange={(event) => setNewLocation(event.target.value)} />
              </div>
            </div>
            <button type="button" disabled={busy} onClick={() => void addEvent()}>
              Schedule
            </button>
          </div>
        ) : null}
      </div>

      <div className="section-title">Alumni profiles</div>
      <div className="card">
        {state !== "loading" && profiles.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__title">No alumni profiles yet</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Student</th>
                  <th>Employer</th>
                  <th>Status</th>
                  <th>Contactable</th>
                </tr>
              </thead>
              <tbody>
                {profiles.map((profile) => (
                  <tr key={profile.id}>
                    <td className="cell-primary">
                      {profile.student_name}
                      <div className="text-sm muted" style={{ fontFamily: "var(--mono)" }}>
                        {profile.student_number}
                      </div>
                    </td>
                    <td>{profile.current_employer || "—"}</td>
                    <td style={{ textTransform: "capitalize" }}>{profile.employment_status.replace(/_/g, " ")}</td>
                    <td>{profile.is_contactable ? "Yes" : "No"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="section-title">Events</div>
      <div className="card">
        {state !== "loading" && events.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__title">No events scheduled</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Event</th>
                  <th>Date</th>
                  <th>Location</th>
                </tr>
              </thead>
              <tbody>
                {events.map((event) => (
                  <tr key={event.id}>
                    <td className="cell-primary">{event.title}</td>
                    <td>{event.event_date}</td>
                    <td>{event.location || "—"}</td>
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
