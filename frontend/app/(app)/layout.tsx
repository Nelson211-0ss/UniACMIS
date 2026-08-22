"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { ConnectionStatus } from "@/components/ConnectionStatus";
import { UserMenu } from "@/components/UserMenu";
import {
  BellIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  GraduationCapIcon,
  MenuIcon,
  XIcon,
} from "@/components/icons";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { visibleNav } from "@/lib/nav";
import * as outbox from "@/lib/outbox";

export default function AppLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { user, loading, signOut, can, hasRole } = useAuth();
  const [navOpen, setNavOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [queued, setQueued] = useState(0);
  const [noticeCount, setNoticeCount] = useState(0);
  const [studentPhoto, setStudentPhoto] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  const isStudent = hasRole("student");
  const isApplicant = hasRole("applicant");

  /** Which portal this is, shown beside the product name in the header. */
  const portalName = isApplicant
    ? "Application Portal"
    : isStudent
      ? "Student Portal"
      : "Staff Portal";
  const home = isApplicant ? "/apply" : isStudent ? "/my" : "/dashboard";

  useEffect(() => {
    if (!isStudent) return;
    api
      .myStudent()
      .then((student) => setStudentPhoto(student?.photo ?? null))
      .catch(() => undefined);
  }, [isStudent]);

  // The badge counts announcements this account can actually see. There is no
  // per-user read state in the backend, so this is "notices addressed to you",
  // not "unread" — inventing an unread count would be worse than counting what
  // is really there.
  useEffect(() => {
    api
      .announcements("?page_size=1")
      .then((page) => setNoticeCount(page.count))
      .catch(() => undefined);
  }, []);

  // Close the mobile drawer on navigation, so a link tap doesn't leave it open
  // over the next page.
  useEffect(() => setNavOpen(false), [pathname]);

  useEffect(() => {
    const refresh = () => void outbox.countPending().then(setQueued);
    refresh();
    return outbox.subscribe(refresh);
  }, []);

  if (loading || !user) {
    return (
      <main className="splash">
        <div className="splash__card">
          <span className="spinner" style={{ width: 28, height: 28 }} aria-hidden="true" />
          <p className="login__sub" style={{ marginTop: 16, marginBottom: 0 }}>
            Loading…
          </p>
        </div>
      </main>
    );
  }

  // Navigation is filtered by permission for usability. The API is the actual
  // boundary — a hidden link is not a security control.
  const visible = visibleNav(can, hasRole);
  const sections = [...new Set(visible.map((item) => item.section))];

  return (
    <div className="app">
      <div className={`nav-backdrop ${navOpen ? "is-open" : ""}`} onClick={() => setNavOpen(false)} />

      <aside className={`sidebar ${navOpen ? "is-open" : ""} ${collapsed ? "is-collapsed" : ""}`}>
        <div className="sidebar__brand">
          <Link href={home} className="sidebar__brand-link">
            <span className="sidebar__brand-mark">
              <GraduationCapIcon size={20} />
            </span>
            <span className="sidebar__brand-text">
              <span className="sidebar__brand-name">University of Juba</span>
              <span className="sidebar__brand-sub">Advance • Transform • Excel</span>
            </span>
          </Link>
          <button
            type="button"
            className="sidebar__collapse-btn icon-btn"
            onClick={() => setCollapsed((v) => !v)}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? <ChevronRightIcon size={16} /> : <ChevronLeftIcon size={16} />}
          </button>
        </div>

        <nav className="sidebar__nav" aria-label="Main">
          {sections.map((section) => (
            <div key={section}>
              <div className="nav__section">{section}</div>
              {visible
                .filter((item) => item.section === section)
                .map((item) => {
                  const Icon = item.icon;
                  const active = pathname === item.href;
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      className="nav__link"
                      title={collapsed ? item.label : undefined}
                      aria-current={active ? "page" : undefined}
                    >
                      <Icon size={18} />
                      <span className="nav__link-label">{item.label}</span>
                      {item.href === "/outbox" && queued > 0 ? (
                        <span className="nav__badge">{queued}</span>
                      ) : null}
                    </Link>
                  );
                })}
            </div>
          ))}
        </nav>

        <div className="sidebar__footer">
          <UserMenu
            user={user}
            align="up"
            photoUrl={studentPhoto}
            onSignOut={() => void signOut().then(() => router.replace("/login"))}
          />
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <button
            type="button"
            className="topbar__menu-btn icon-btn"
            onClick={() => setNavOpen((v) => !v)}
            aria-label={navOpen ? "Close menu" : "Open menu"}
            aria-expanded={navOpen}
          >
            {navOpen ? <XIcon /> : <MenuIcon />}
          </button>

          <Link href={home} className="topbar__portal">
            <span className="topbar__portal-name">ACMIS</span>
            <span className="topbar__portal-sub">{portalName}</span>
          </Link>

          <span className="topbar__spacer" />

          <div className="topbar__actions">
            <ConnectionStatus />
            <Link href="/communications" className="topbar__notify">
              <BellIcon size={18} />
              <span className="topbar__label">Notifications</span>
              {noticeCount > 0 ? <span className="topbar__notify-count">{noticeCount}</span> : null}
            </Link>
            <span className="topbar__user">
              <UserMenu
                user={user}
                photoUrl={studentPhoto}
                onSignOut={() => void signOut().then(() => router.replace("/login"))}
              />
            </span>
          </div>
        </header>

        <main className="content">{children}</main>
      </div>
    </div>
  );
}
