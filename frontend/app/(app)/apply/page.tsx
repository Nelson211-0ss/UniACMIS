"use client";

/**
 * Applicant portal (FR-ADM-01, FR-ADM-04, FR-ADM-07).
 *
 * One page an applicant can live in from account creation to decision: where
 * their application has got to, what is still blocking it, and the actions that
 * move it forward. The stepper is derived from the application's real status
 * and timestamps rather than stored separately, so it cannot drift from what
 * the admissions office sees.
 *
 * The fee is the gate: `submit_application` refuses until it is confirmed, and
 * confirmation is the provider's word rather than ours — so the page polls and
 * reports what came back instead of assuming a click settled anything.
 */

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  AlertCircleIcon,
  BuildingIcon,
  CheckCircleIcon,
  CreditCardIcon,
  FileTextIcon,
  MegaphoneIcon,
  UploadIcon,
} from "@/components/icons";
import { ApiFailure, api } from "@/lib/api";
import type { ApplicationDetail } from "@/lib/api";

const STATUS_PILL: Record<string, string> = {
  draft: "",
  submitted: "pill--pending",
  under_review: "pill--info",
  offered: "pill--info",
  accepted: "pill--synced",
  enrolled: "pill--synced",
  rejected: "pill--failed",
  withdrawn: "pill--failed",
};

type StepState = "done" | "current" | "todo";

function errorText(error: unknown, fallback: string) {
  return error instanceof ApiFailure ? error.error.message : fallback;
}

function shortDate(value: string | null) {
  return value ? new Date(value).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "";
}

/** The five stages the reference design shows, resolved from one application. */
function buildSteps(app: ApplicationDetail | null) {
  if (!app) return [];
  const submitted = app.status !== "draft" && app.status !== "withdrawn";
  const verified = app.documents.length > 0;
  const reviewing = ["under_review", "offered", "accepted", "rejected", "enrolled"].includes(app.status);
  const decided = ["offered", "accepted", "rejected", "enrolled"].includes(app.status);

  const rows: Array<{ label: string; when: string; state: StepState }> = [
    { label: "Account Created", when: shortDate(app.created_at), state: "done" },
    {
      label: "Application Submitted",
      when: submitted ? shortDate(app.submitted_at) : "Pending",
      state: submitted ? "done" : "current",
    },
    {
      label: "Documents Uploaded",
      when: verified ? `${app.documents.length} on file` : "None yet",
      state: verified ? "done" : submitted ? "current" : "todo",
    },
    {
      label: "Under Review",
      when: reviewing ? "In progress" : "Pending",
      state: reviewing && !decided ? "current" : reviewing ? "done" : "todo",
    },
    {
      label: "Decision",
      when: decided ? app.status.replace(/_/g, " ") : "Pending",
      state: decided ? "done" : "todo",
    },
  ];
  return rows;
}

export default function ApplicantPortalPage() {
  const [app, setApp] = useState<ApplicationDetail | null>(null);
  const [notices, setNotices] = useState<Array<{ id: number; title: string; body: string; sent_at: string }>>([]);
  const [state, setState] = useState<"loading" | "ready" | "empty" | "offline" | "error">("loading");
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      // Scoped to the signed-in applicant server-side, so "the first one" is
      // theirs — an applicant has one application per intake in practice.
      const page = await api.applications("?page_size=5");
      if (page.results.length === 0) {
        setState("empty");
        return;
      }
      setApp(await api.application(page.results[0].id));
      setState("ready");
    } catch (error) {
      setState(error instanceof ApiFailure && error.offline ? "offline" : "error");
    }
  }

  useEffect(() => {
    void load();
    void api
      .announcements("?page_size=3")
      .then((page) => setNotices(page.results))
      .catch(() => undefined);
  }, []);

  async function act(fn: () => Promise<unknown>, success: string | ((result: never) => string)) {
    setBusy(true);
    setNotice(null);
    try {
      const result = await fn();
      setNotice({ kind: "success", text: typeof success === "function" ? success(result as never) : success });
      await load();
    } catch (error) {
      setNotice({ kind: "error", text: errorText(error, "That action could not be completed.") });
    } finally {
      setBusy(false);
    }
  }

  const steps = buildSteps(app);
  const pendingFee = app?.fee_payments.find((p) => p.status === "pending") ?? null;
  const canEdit = app?.status === "draft";

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Good day{app ? `, ${app.first_name}` : ""} 👋</h1>
          <p className="page-subtitle">Track and manage your admission application</p>
        </div>
        {app ? (
          <span className={`pill ${STATUS_PILL[app.status] ?? ""}`}>{app.status.replace(/_/g, " ")}</span>
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
      {state === "error" ? (
        <div className="alert alert--error">
          <span>Could not load your application. Try again shortly.</span>
        </div>
      ) : null}

      {state === "empty" ? (
        <div className="card">
          <div className="empty-state">
            <span className="empty-state__title">No application on file yet</span>
            <p className="muted">
              An application is opened for you by the admissions office, or by you through the public admissions form.
              Once it exists, its progress appears here.
            </p>
          </div>
        </div>
      ) : null}

      {/* -------------------------------------------------------- progress */}
      {app ? (
        <div className="card">
          <div className="panel__head">
            <h2>Application Progress</h2>
            <span className="text-sm muted" style={{ fontFamily: "var(--mono)" }}>
              {app.reference_number}
            </span>
          </div>
          <ol className="stepper">
            {steps.map((step) => (
              <li
                key={step.label}
                className={`stepper__step ${step.state === "done" ? "is-done" : ""} ${
                  step.state === "current" ? "is-current" : ""
                }`}
              >
                <span className="stepper__dot">
                  {step.state === "done" ? <CheckCircleIcon size={15} /> : null}
                </span>
                <span className="stepper__body">
                  <span className="stepper__label">{step.label}</span>
                  <span className="stepper__when">{step.when}</span>
                </span>
              </li>
            ))}
          </ol>
        </div>
      ) : null}

      {/* --------------------------------------------------- what to do next */}
      {app ? (
        <div className="grid grid--stats">
          <div className="card actioncard">
            <span className="figure__tile figure__tile--green">
              <FileTextIcon size={20} />
            </span>
            <span className="actioncard__title">Application details</span>
            <span className="actioncard__text">
              {canEdit
                ? "Complete or correct your details before submitting."
                : "Submitted — details can no longer be edited directly."}
            </span>
            <span className="text-sm muted">
              {app.programme_code} · {app.phone || "no phone on file"}
            </span>
          </div>

          <div className="card actioncard">
            <span className="figure__tile figure__tile--amber">
              <UploadIcon size={20} />
            </span>
            <span className="actioncard__title">Supporting documents</span>
            <span className="actioncard__text">
              {app.documents.length === 0
                ? "No documents uploaded yet. Certificates and an ID are normally required."
                : `${app.documents.length} document${app.documents.length === 1 ? "" : "s"} on file.`}
            </span>
            <span className="text-sm muted">Upload at the admissions office</span>
          </div>

          <div className="card actioncard">
            <span className="figure__tile figure__tile--red">
              <CreditCardIcon size={20} />
            </span>
            <span className="actioncard__title">Application fee</span>
            <span className="actioncard__text">
              {app.fee_paid
                ? "Paid and confirmed."
                : pendingFee
                  ? `Awaiting confirmation of ${pendingFee.amount} ${pendingFee.currency}.`
                  : "Not yet paid. The fee must clear before you can submit."}
            </span>
            {!app.fee_paid && pendingFee ? (
              <button
                type="button"
                className="sm secondary"
                disabled={busy}
                onClick={() =>
                  void act(
                    () => api.confirmApplicationFee(app.id, pendingFee.reference),
                    (result: { status: string }) =>
                      result.status === "confirmed"
                        ? "Fee confirmed."
                        : result.status === "failed"
                          ? "The provider reports this payment failed."
                          : "Still pending with the provider — check again in a moment.",
                  )
                }
              >
                Check payment
              </button>
            ) : null}
          </div>

          <div className="card actioncard">
            <span className="figure__tile figure__tile--blue">
              <CheckCircleIcon size={20} />
            </span>
            <span className="actioncard__title">Submit</span>
            <span className="actioncard__text">
              {app.status === "draft"
                ? app.fee_paid
                  ? "Everything needed is in place."
                  : "Blocked until the application fee is confirmed."
                : "Already submitted for review."}
            </span>
            {app.status === "draft" ? (
              <button
                type="button"
                className="sm"
                disabled={busy || !app.fee_paid}
                onClick={() => void act(() => api.submitApplication(app.id), "Application submitted for review.")}
              >
                Submit application
              </button>
            ) : null}
          </div>
        </div>
      ) : null}

      {/* ----------------------------------------- summary + notifications */}
      {app ? (
        <div className="duo">
          <div className="card">
            <div className="panel__head">
              <h2>Application Summary</h2>
            </div>
            <table className="detail">
              <tbody>
                <tr>
                  <th scope="row">Application number</th>
                  <td style={{ fontFamily: "var(--mono)" }}>{app.reference_number}</td>
                </tr>
                <tr>
                  <th scope="row">Programme</th>
                  <td>{app.programme_code}</td>
                </tr>
                <tr>
                  <th scope="row">Applicant</th>
                  <td>{app.full_name}</td>
                </tr>
                <tr>
                  <th scope="row">Application date</th>
                  <td>{shortDate(app.created_at)}</td>
                </tr>
                <tr>
                  <th scope="row">Fee</th>
                  <td className={app.fee_paid ? "is-green" : "is-red"}>{app.fee_paid ? "Paid" : "Outstanding"}</td>
                </tr>
                <tr>
                  <th scope="row">Current status</th>
                  <td>{app.status.replace(/_/g, " ")}</td>
                </tr>
                {app.score ? (
                  <tr>
                    <th scope="row">Committee score</th>
                    <td>{app.score}</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>

          <div className="card">
            <div className="panel__head">
              <h2>Recent Notifications</h2>
              <Link href="/communications" className="panel__link">
                View All →
              </Link>
            </div>
            {app.decision_reason ? (
              <div className="alert alert--info" style={{ marginBottom: "var(--sp-4)" }}>
                <span>{app.decision_reason}</span>
              </div>
            ) : null}
            {notices.length === 0 ? (
              <div className="empty-state">
                <span className="empty-state__title">No notices yet</span>
              </div>
            ) : (
              <ul className="notifs">
                {notices.map((item, index) => (
                  <li key={item.id} className="notifs__item">
                    <span
                      className={`notifs__tile ${
                        index % 3 === 1 ? "notifs__tile--red" : index % 3 === 2 ? "notifs__tile--blue" : ""
                      }`}
                    >
                      <MegaphoneIcon size={15} />
                    </span>
                    <span className="notifs__body">
                      <span className="notifs__title">{item.title}</span>
                      <span className="notifs__text">{item.body}</span>
                      <span className="notifs__when">{shortDate(item.sent_at)}</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ) : null}

      {/* ---------------------------------------------- offer, if there is one */}
      {app?.status === "offered" ? (
        <div className="card">
          <div className="panel__head">
            <h2>You have an offer</h2>
          </div>
          <p className="muted" style={{ marginTop: 0 }}>
            Accepting converts your application into a student record. Declining closes it.
          </p>
          <div style={{ display: "flex", gap: "var(--sp-2)", flexWrap: "wrap" }}>
            <button
              type="button"
              disabled={busy}
              onClick={() => void act(() => api.acceptOffer(app.id), "Offer accepted.")}
            >
              Accept offer
            </button>
            <button
              type="button"
              className="danger"
              disabled={busy}
              onClick={() => void act(() => api.declineOffer(app.id), "Offer declined.")}
            >
              Decline
            </button>
          </div>
        </div>
      ) : null}

      {/* ------------------------------------------------------- assistance */}
      <div className="assist">
        <div className="assist__body">
          <h2>Need assistance?</h2>
          <p>Our admissions team can help you through any part of your application.</p>
          <Link href="/communications" className="button primary">
            Contact admissions
          </Link>
        </div>
        <span className="assist__mark">
          <BuildingIcon size={56} />
        </span>
      </div>

      {app?.status === "draft" && !app.fee_paid && !pendingFee ? (
        <div className="alert alert--warning">
          <AlertCircleIcon size={16} />
          <span>
            No application fee has been recorded yet. The admissions office raises it when you apply — contact them if
            this looks wrong.
          </span>
        </div>
      ) : null}
    </>
  );
}
