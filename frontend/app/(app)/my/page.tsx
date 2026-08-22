"use client";

/**
 * Student self-service portal — overview (FR-STU-01…14 / checklist §4.16).
 *
 * Consolidates what a student needs in one place. Every section below is
 * backed by a real API call — fees, library, hostel and graduation
 * clearance included, now that those modules exist. The student's own
 * identity (name, photo, programme) is the portal layout's header, not
 * this page's — see `layout.tsx`.
 */

import Link from "next/link";
import { useEffect, useState } from "react";

import { CountUp } from "@/components/CountUp";
import { Stamp } from "@/components/Stamp";
import {
  BedIcon,
  BookOpenIcon,
  CalendarIcon,
  ClockIcon,
  CreditCardIcon,
  FileTextIcon,
  LayersIcon,
  UserPlusIcon,
} from "@/components/icons";
import { ApiFailure, api } from "@/lib/api";

import { useStudent } from "./student-context";

const QUICK_LINKS = [
  { href: "/my/timetable", label: "My timetable", icon: CalendarIcon, description: "Weekly classes and the exam schedule." },
  { href: "/my/attendance", label: "My attendance", icon: ClockIcon, description: "Session attendance and exam eligibility." },
  { href: "/my/results", label: "Results & appeals", icon: LayersIcon, description: "Published grades, GPA and grade appeals." },
  { href: "/my/finance", label: "Fees & payments", icon: CreditCardIcon, description: "Invoices, receipts and your balance." },
  { href: "/library", label: "Library", icon: BookOpenIcon, description: "The catalogue and your loans." },
  { href: "/hostel", label: "Hostel", icon: BedIcon, description: "Your room allocation." },
  { href: "/documents", label: "Documents", icon: FileTextIcon, description: "Transcript requests and clearance." },
];

export default function StudentPortalPage() {
  const { student } = useStudent();
  const [semester, setSemester] = useState<{ id: number; name: string } | null>(null);
  const [registrationOpen, setRegistrationOpen] = useState(false);
  const [registeredCount, setRegisteredCount] = useState<number | null>(null);
  const [gpa, setGpa] = useState<string | null | undefined>(undefined);
  const [resultsPublished, setResultsPublished] = useState<boolean | null>(null);
  const [balance, setBalance] = useState<string | null>(null);
  const [currency, setCurrency] = useState("SSP");
  const [clear, setClear] = useState<boolean | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    if (!student) return;
    const currentStudent = student;
    let cancelled = false;

    async function load() {
      try {
        const calendar = await api.calendar();
        if (cancelled) return;
        setSemester(calendar.semester);
        setRegistrationOpen(calendar.registration_open);

        if (calendar.semester) {
          const [registrations, result] = await Promise.all([
            api.myRegistrations(calendar.semester.id).catch(() => null),
            api.studentResult(currentStudent.id, calendar.semester.id).catch(() => null),
          ]);
          if (cancelled) return;
          if (registrations) {
            setRegisteredCount(
              registrations.results.filter((r) => r.status === "registered").length,
            );
          }
          if (result) {
            setResultsPublished(result.published && !result.withheld);
            setGpa(result.gpa);
          }
          const [feeBalance, clearance] = await Promise.all([
            api.myFeeBalance(currentStudent.id).catch(() => null),
            api.myClearance(currentStudent.id).catch(() => null),
          ]);
          if (cancelled) return;
          if (feeBalance) {
            setBalance(feeBalance.balance);
            setCurrency(feeBalance.currency);
          }
          if (clearance) setClear(clearance.clear);
        }
      } catch (error) {
        if (error instanceof ApiFailure && error.offline) setOffline(true);
      } finally {
        if (!cancelled) setLoaded(true);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [student]);

  return (
    <>
      <div className="page-header">
        <div>
          <h1>My portal</h1>
          <p className="page-subtitle">{semester ? semester.name : "Your standing at a glance"}</p>
        </div>
      </div>

      {offline ? (
        <div className="alert alert--warning">
          <span>Working offline — figures below may be out of date.</span>
        </div>
      ) : null}

      <div className="grid">
        <div className="card stat stat--accent-teal">
          <div className="stat__top">
            <span className="stat__label">Registered this semester</span>
            <span className="stat__icon">
              <UserPlusIcon size={18} />
            </span>
          </div>
          <div className="stat__value">
            {loaded ? (registeredCount !== null ? <CountUp value={registeredCount} duration={500} /> : "—") : "…"}
          </div>
          <div className="stat__foot">
            <Link href="/my/courses">Manage registration →</Link>
          </div>
        </div>

        <div className="card stat stat--accent-amber">
          <div className="stat__top">
            <span className="stat__label">Cumulative GPA</span>
            <span className="stat__icon">
              <ClockIcon size={18} />
            </span>
          </div>
          <div className="stat__value">
            {loaded ? (resultsPublished ? gpa ?? "—" : "—") : "…"}
          </div>
          <div className="stat__foot">
            {loaded && !resultsPublished
              ? "Not published for the current semester yet"
              : <Link href="/my/results">View results →</Link>}
          </div>
        </div>

        {loaded && balance !== null ? (
          <div className={`card stat stat--accent-${Number(balance) > 0 ? "red" : "teal"}`}>
            <div className="stat__top">
              <span className="stat__label">Fee balance</span>
              <span className="stat__icon">
                <CreditCardIcon size={18} />
              </span>
            </div>
            <div className="stat__value">
              {Number(balance) > 0 ? (
                <>
                  <CountUp value={Number(balance)} /> <span style={{ fontSize: "0.6em" }}>{currency}</span>
                </>
              ) : (
                "0"
              )}
            </div>
            <div className="stat__foot">
              <Link href="/my/finance">View invoices →</Link>
            </div>
          </div>
        ) : null}

        {loaded && clear !== null ? (
          <div className={`card stat stat--accent-${clear ? "teal" : "orange"}`}>
            <div className="stat__top">
              <span className="stat__label">Graduation clearance</span>
              <span className="stat__icon">
                <FileTextIcon size={18} />
              </span>
            </div>
            <div className="stat__value" style={{ fontSize: "1.25rem" }}>
              {clear ? "Clear" : "Holds outstanding"}
            </div>
            <div className="stat__foot">
              <Link href="/documents">View documents →</Link>
            </div>
          </div>
        ) : null}
      </div>

      {semester ? (
        <div className="card" style={{ display: "flex", alignItems: "center", gap: 24, flexWrap: "wrap" }}>
          <Stamp
            status={registrationOpen ? "verified" : "hold"}
            label={registrationOpen ? "Open" : "Closed"}
            size="sm"
          />
          <div>
            <h2>Registration {registrationOpen ? "is open" : "is closed"}</h2>
            <p className="muted" style={{ margin: "4px 0 0" }}>
              {semester.name}. {registrationOpen ? "You may register or drop courses." : "Come back when the window opens."}
            </p>
          </div>
        </div>
      ) : null}

      <div className="dashboard-section">
        <h2>Quick links</h2>
      </div>
      <div className="grid grid--compact">
        {QUICK_LINKS.map(({ href, label, icon: Icon, description }) => (
          <Link key={href} href={href} className="card card--interactive quick-link" style={{ margin: 0 }}>
            <span className="quick-link__icon">
              <Icon size={18} />
            </span>
            <span className="quick-link__body">
              <span className="quick-link__title">{label}</span>
              <span className="quick-link__desc">{description}</span>
            </span>
          </Link>
        ))}
      </div>
    </>
  );
}
