"use client";

/**
 * Offline-capable student admission (FR-REG-01, NFR-AVAIL-01).
 *
 * The end-to-end proof of the offline spine. A clerk working through paper forms
 * during an outage types here; entries queue on the device and are sent when the
 * link returns, exactly once.
 *
 * The rule the UI must never break: a queued entry is shown as **pending**, never
 * as saved. The student ID is issued by the server, so until it syncs there is no
 * student number to report — claiming otherwise would have clerks writing an
 * invented number onto a paper file.
 */

import { useEffect, useState } from "react";

import {
  AlertCircleIcon,
  CheckCircleIcon,
  LayersIcon,
  MapPinIcon,
  PhoneIcon,
  UserIcon,
  WifiOffIcon,
} from "@/components/icons";
import { ApiFailure, api } from "@/lib/api";
import * as outbox from "@/lib/outbox";
import { flush } from "@/lib/sync";

interface Option {
  id: number;
  label: string;
}

const STATES = [
  ["central_equatoria", "Central Equatoria"],
  ["eastern_equatoria", "Eastern Equatoria"],
  ["western_equatoria", "Western Equatoria"],
  ["jonglei", "Jonglei"],
  ["unity", "Unity"],
  ["upper_nile", "Upper Nile"],
  ["warrap", "Warrap"],
  ["northern_bahr_el_ghazal", "Northern Bahr el Ghazal"],
  ["western_bahr_el_ghazal", "Western Bahr el Ghazal"],
  ["lakes", "Lakes"],
  ["abyei", "Abyei Administrative Area"],
  ["greater_pibor", "Greater Pibor Administrative Area"],
  ["ruweng", "Ruweng Administrative Area"],
  ["outside", "Outside South Sudan"],
];

const EMPTY_FORM = {
  first_name: "",
  middle_name: "",
  last_name: "",
  gender: "female",
  date_of_birth: "",
  national_id_number: "",
  state_of_origin: "",
  county: "",
  phone: "",
  email: "",
  programme_id: "",
  entry_academic_year_id: "",
};

const NOTICE_ICON = {
  success: CheckCircleIcon,
  warning: WifiOffIcon,
  error: AlertCircleIcon,
} as const;

export default function AdmitStudentPage() {
  const [form, setForm] = useState(EMPTY_FORM);
  const [programmes, setProgrammes] = useState<Option[]>([]);
  const [years, setYears] = useState<Option[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ kind: keyof typeof NOTICE_ICON; text: string } | null>(
    null,
  );
  const [referenceLoadFailed, setReferenceLoadFailed] = useState(false);

  useEffect(() => {
    // Reference data is cached by the service worker, so these usually resolve
    // even offline once the page has been visited while online.
    Promise.all([api.programmes(), api.academicYears()])
      .then(([programmePage, yearPage]) => {
        setProgrammes(
          programmePage.results.map((p) => ({ id: p.id, label: `${p.code} — ${p.name}` })),
        );
        const yearOptions = yearPage.results.map((y) => ({
          id: y.id,
          label: y.is_current ? `${y.name} (current)` : y.name,
        }));
        setYears(yearOptions);

        const current = yearPage.results.find((y) => y.is_current);
        if (current) {
          setForm((previous) => ({
            ...previous,
            entry_academic_year_id: String(current.id),
          }));
        }
      })
      .catch(() => setReferenceLoadFailed(true));
  }, []);

  function set(field: keyof typeof EMPTY_FORM, value: string) {
    setForm((previous) => ({ ...previous, [field]: value }));
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setNotice(null);

    const payload: Record<string, unknown> = {
      programme_id: Number(form.programme_id),
      entry_academic_year_id: Number(form.entry_academic_year_id),
      first_name: form.first_name.trim(),
      middle_name: form.middle_name.trim(),
      last_name: form.last_name.trim(),
      gender: form.gender,
      national_id_number: form.national_id_number.trim(),
      state_of_origin: form.state_of_origin,
      county: form.county.trim(),
      phone: form.phone.trim(),
      email: form.email.trim(),
    };
    if (form.date_of_birth) payload.date_of_birth = form.date_of_birth;

    const label = `${form.first_name} ${form.last_name}`.trim();

    try {
      // Always queue first, then attempt to send. Writing to IndexedDB before the
      // network call is what guarantees nothing is lost if the connection (or the
      // power) dies mid-request.
      const operation = await outbox.enqueue("registry.student", "create", payload, label);

      const summary = await flush(true);

      const stored = (await outbox.all()).find(
        (op) => op.clientOpId === operation.clientOpId,
      );

      if (stored?.status === "synced") {
        const studentId = stored.result?.student_id ?? "(issued)";
        setNotice({
          kind: "success",
          text: `${label} admitted. Student ID ${studentId}.`,
        });
      } else if (summary.offline || !navigator.onLine) {
        setNotice({
          kind: "warning",
          text:
            `${label} is queued on this device — not yet saved on the server. ` +
            "It will be sent automatically when the connection returns, and the " +
            "student ID will be issued then.",
        });
      } else {
        setNotice({
          kind: "error",
          text:
            stored?.lastError ??
            `${label} could not be saved. It stays in the queue — check the offline queue page.`,
        });
      }

      if (stored?.status === "synced" || summary.offline) {
        setForm({
          ...EMPTY_FORM,
          entry_academic_year_id: form.entry_academic_year_id,
          programme_id: form.programme_id,
        });
      }
    } catch (caught) {
      setNotice({
        kind: "error",
        text:
          caught instanceof ApiFailure
            ? caught.error.message
            : "Could not queue this entry on the device.",
      });
    } finally {
      setBusy(false);
    }
  }

  const NoticeIcon = notice ? NOTICE_ICON[notice.kind] : null;

  return (
    <>
      <h1>Admit a student</h1>
      <p className="page-subtitle">
        Works offline. Entries are held on this device and sent when a connection is
        available.
      </p>

      {notice && NoticeIcon ? (
        <div className={`alert alert--${notice.kind}`} role="status">
          <NoticeIcon size={18} />
          <span>{notice.text}</span>
        </div>
      ) : null}

      {referenceLoadFailed ? (
        <div className="alert alert--warning">
          <AlertCircleIcon size={18} />
          <span>
            Programmes and academic years could not be loaded. Open this page once
            while online so they are cached for offline use.
          </span>
        </div>
      ) : null}

      <form onSubmit={onSubmit}>
        <div className="card">
          <div className="section-title">
            <LayersIcon size={16} />
            Programme &amp; intake
          </div>

          <div className="field-row">
            <div className="field">
              <label htmlFor="programme">Programme *</label>
              <select
                id="programme"
                required
                value={form.programme_id}
                onChange={(event) => set("programme_id", event.target.value)}
              >
                <option value="">Select…</option>
                {programmes.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label htmlFor="year">Intake year *</label>
              <select
                id="year"
                required
                value={form.entry_academic_year_id}
                onChange={(event) => set("entry_academic_year_id", event.target.value)}
              >
                <option value="">Select…</option>
                {years.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="section-title">
            <UserIcon size={16} />
            Personal details
          </div>

          <div className="field-row">
            <div className="field">
              <label htmlFor="first_name">First name *</label>
              <input
                id="first_name"
                required
                value={form.first_name}
                onChange={(event) => set("first_name", event.target.value)}
              />
            </div>

            <div className="field">
              <label htmlFor="middle_name">Middle name</label>
              <input
                id="middle_name"
                value={form.middle_name}
                onChange={(event) => set("middle_name", event.target.value)}
              />
              <div className="hint">Kept separate so certificates print correctly.</div>
            </div>

            <div className="field">
              <label htmlFor="last_name">Last name *</label>
              <input
                id="last_name"
                required
                value={form.last_name}
                onChange={(event) => set("last_name", event.target.value)}
              />
            </div>
          </div>

          <div className="field-row">
            <div className="field">
              <label htmlFor="gender">Gender *</label>
              <select
                id="gender"
                required
                value={form.gender}
                onChange={(event) => set("gender", event.target.value)}
              >
                <option value="female">Female</option>
                <option value="male">Male</option>
                <option value="other">Other</option>
                <option value="undisclosed">Prefer not to say</option>
              </select>
            </div>

            <div className="field">
              <label htmlFor="dob">Date of birth</label>
              <input
                id="dob"
                type="date"
                value={form.date_of_birth}
                onChange={(event) => set("date_of_birth", event.target.value)}
              />
            </div>

            <div className="field">
              <label htmlFor="nid">National ID number</label>
              <input
                id="nid"
                value={form.national_id_number}
                onChange={(event) => set("national_id_number", event.target.value)}
              />
              <div className="hint">
                Used to catch the same person being entered twice from two devices.
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="section-title">
            <MapPinIcon size={16} />
            Origin &amp; special needs
          </div>

          <div className="field-row">
            <div className="field">
              <label htmlFor="state">State of origin</label>
              <select
                id="state"
                value={form.state_of_origin}
                onChange={(event) => set("state_of_origin", event.target.value)}
              >
                <option value="">Select…</option>
                {STATES.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <div className="hint">Required for statutory returns to MoHEST.</div>
            </div>

            <div className="field">
              <label htmlFor="county">County</label>
              <input
                id="county"
                value={form.county}
                onChange={(event) => set("county", event.target.value)}
              />
            </div>
          </div>
        </div>

        <div className="card">
          <div className="section-title">
            <PhoneIcon size={16} />
            Contact
          </div>

          <div className="field-row">
            <div className="field">
              <label htmlFor="phone">Phone</label>
              <input
                id="phone"
                type="tel"
                inputMode="tel"
                placeholder="+211…"
                value={form.phone}
                onChange={(event) => set("phone", event.target.value)}
              />
              <div className="hint">The channel used for critical notices by SMS.</div>
            </div>

            <div className="field">
              <label htmlFor="email">Email</label>
              <input
                id="email"
                type="email"
                inputMode="email"
                value={form.email}
                onChange={(event) => set("email", event.target.value)}
              />
            </div>
          </div>

          <div className="form-actions">
            <button type="submit" className="primary" disabled={busy}>
              {busy ? <span className="spinner" aria-hidden="true" /> : null}
              {busy ? "Saving…" : "Admit student"}
            </button>
          </div>
        </div>
      </form>
    </>
  );
}
