"use client";

/**
 * Student self-service portal — overview (FR-STU-01…14 / checklist §4.16).
 *
 * Consolidates what a student needs in one place. Every section below is
 * backed by a real API call — fees, library, hostel and graduation
 * clearance included, now that those modules exist.
 */

import Link from "next/link";
import { useEffect, useState } from "react";

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
import { useAuth } from "@/lib/auth";

interface Student {
  id: number;
  student_id: string;
  full_name: string;
  programme_code: string;
  programme_name: string;
  current_level: number;
  status: string;
}

const QUICK_LINKS = [
  { href: "/my/finance", label: "Fees & payments", icon: CreditCardIcon, description: "Invoices, receipts and your balance." },
  { href: "/library", label: "Library", icon: BookOpenIcon, description: "The catalogue and your loans." },
  { href: "/hostel", label: "Hostel", icon: BedIcon, description: "Your room allocation." },
  { href: "/documents", label: "Documents", icon: FileTextIcon, description: "Transcript requests and clearance." },
];

export default function StudentPortalPage() {
  const { user } = useAuth();
  const [student, setStudent] = useState<Student | null>(null);
  const [semester, setSemester] = useState<{ id: number; name: string } | null>(null);
  const [registrationOpen, setRegistrationOpen] = useState(false);
  const [registeredCount, setRegisteredCount] = useState<number | null>(null);
  const [gpa, setGpa] = useState<string | null | undefined>(undefined);
  const [resultsPublished, setResultsPublished] = useState<boolean | null>(null);
  const [balance, setBalance] = useState<string | null>(null);
  const [clear, setClear] = useState<boolean | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [me, calendar] = await Promise.all([api.myStudent(), api.calendar()]);
        if (cancelled) return;
        setStudent(me);
        setSemester(calendar.semester);
        setRegistrationOpen(calendar.registration_open);

        if (me && calendar.semester) {
          const [registrations, result] = await Promise.all([
            api.myRegistrations(calendar.semester.id).catch(() => null),
            api.studentResult(me.id, calendar.semester.id).catch(() => null),
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
            api.myFeeBalance(me.id).catch(() => null),
            api.myClearance(me.id).catch(() => null),
          ]);
          if (cancelled) return;
          if (feeBalance) setBalance(feeBalance.balance);
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
  }, []);

  return (
    <>
      <div className="page-header">
        <div>
          <h1>My portal</h1>
          <p className="page-subtitle">
            {student ? `${student.programme_name} · Year ${student.current_level}` : "Loading…"}
          </p>
        </div>
      </div>

      {offline ? (
        <div className="alert alert--warning">
          <span>Working offline — figures below may be out of date.</span>
        </div>
      ) : null}

      <div className="grid">
        <div className="card stat stat--accent-blue">
          <div className="stat__top">
            <span className="stat__label">Student number</span>
            <span className="stat__icon">
              <LayersIcon size={18} />
            </span>
          </div>
          <div className="stat__value" style={{ fontSize: "1.375rem" }}>
            {student?.student_id ?? "—"}
          </div>
          <div className="stat__foot">{user?.full_name}</div>
        </div>

        <div className="card stat stat--accent-teal">
          <div className="stat__top">
            <span className="stat__label">Registered this semester</span>
            <span className="stat__icon">
              <UserPlusIcon size={18} />
            </span>
          </div>
          <div className="stat__value">{loaded ? registeredCount ?? "—" : "…"}</div>
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
      </div>

      {semester ? (
        <div className="card" style={{ display: "flex", alignItems: "center", gap: 24 }}>
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

      <div className="card">
        <div className="card__header">
          <span className="card__icon">
            <CalendarIcon size={18} />
          </span>
          <h2>Quick links</h2>
        </div>
        <div className="grid">
          <Link href="/my/timetable" className="button secondary block">
            My timetable
          </Link>
          <Link href="/my/attendance" className="button secondary block">
            My attendance
          </Link>
          <Link href="/my/results" className="button secondary block">
            Results &amp; grade appeals
          </Link>
        </div>
      </div>

      {loaded && (balance !== null || clear !== null) ? (
        <div className="grid">
          {balance !== null ? (
            <div className={`card stat stat--accent-${Number(balance) > 0 ? "rose" : "teal"}`}>
              <div className="stat__top">
                <span className="stat__label">Fee balance</span>
                <span className="stat__icon">
                  <CreditCardIcon size={18} />
                </span>
              </div>
              <div className="stat__value">{Number(balance) > 0 ? Number(balance).toLocaleString() : "0"}</div>
              <div className="stat__foot">
                <Link href="/my/finance">View invoices →</Link>
              </div>
            </div>
          ) : null}
          {clear !== null ? (
            <div className={`card stat stat--accent-${clear ? "teal" : "amber"}`}>
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
      ) : null}

      <div className="card">
        <div className="card__header">
          <span className="card__icon">
            <CreditCardIcon size={18} />
          </span>
          <h2>More of your portal</h2>
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
      </div>
    </>
  );
}
