"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { ConnectionStatus } from "@/components/ConnectionStatus";
import { UserMenu } from "@/components/UserMenu";
import {
  AlertCircleIcon,
  CalendarIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ClockIcon,
  DashboardIcon,
  GraduationCapIcon,
  InboxIcon,
  LayersIcon,
  MenuIcon,
  UserPlusIcon,
  UsersIcon,
  XIcon,
} from "@/components/icons";
import { useAuth } from "@/lib/auth";
import * as outbox from "@/lib/outbox";

interface NavItem {
  href: string;
  label: string;
  icon: (props: { size?: number }) => ReactNode;
  /** Permission the API requires for the destination, or null for everyone. */
  permission: string | null;
  /** Shown only to one of these roles, or everyone if omitted. */
  roles?: string[];
  section: string;
}

const NAV: NavItem[] = [
  {
    href: "/dashboard",
    label: "Dashboard",
    icon: DashboardIcon,
    permission: null,
    section: "Overview",
  },
  {
    href: "/my",
    label: "My portal",
    icon: LayersIcon,
    permission: null,
    roles: ["student"],
    section: "Student",
  },
  {
    href: "/my/courses",
    label: "Course registration",
    icon: UserPlusIcon,
    permission: "enrollment.view_courseregistration",
    roles: ["student"],
    section: "Student",
  },
  {
    href: "/my/timetable",
    label: "Timetable",
    icon: CalendarIcon,
    permission: "timetabling.view_timetableentry",
    roles: ["student"],
    section: "Student",
  },
  {
    href: "/my/results",
    label: "Results & appeals",
    icon: LayersIcon,
    permission: "examinations.view_mark",
    roles: ["student"],
    section: "Student",
  },
  {
    href: "/my/attendance",
    label: "Attendance",
    icon: ClockIcon,
    permission: "attendance.view_sessionrecord",
    roles: ["student"],
    section: "Student",
  },
  {
    href: "/students",
    label: "Students",
    icon: UsersIcon,
    permission: "registry.view_student",
    section: "Registry",
  },
  {
    href: "/students/new",
    label: "Admit a student",
    icon: UserPlusIcon,
    permission: "registry.add_student",
    section: "Registry",
  },
  {
    href: "/outbox",
    label: "Offline queue",
    icon: InboxIcon,
    permission: null,
    section: "Device",
  },
];

export default function AppLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { user, loading, signOut, can, hasRole } = useAuth();
  const [navOpen, setNavOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [queued, setQueued] = useState(0);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

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
  const visible = NAV.filter(
    (item) =>
      (!item.permission || can(item.permission)) && (!item.roles || hasRole(...item.roles)),
  );
  const sections = [...new Set(visible.map((item) => item.section))];

  return (
    <div className="app">
      <div className={`nav-backdrop ${navOpen ? "is-open" : ""}`} onClick={() => setNavOpen(false)} />

      <aside className={`sidebar ${navOpen ? "is-open" : ""} ${collapsed ? "is-collapsed" : ""}`}>
        <div className="sidebar__brand">
          <Link href="/dashboard" className="sidebar__brand-link">
            <span className="sidebar__brand-mark">
              <GraduationCapIcon size={18} />
            </span>
            <span className="sidebar__brand-text">
              <span className="sidebar__brand-name">UniACMIS</span>
              <span className="sidebar__brand-sub">Academic Management</span>
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

          <Link href="/dashboard" className="topbar__brand">
            <span className="topbar__brand-mark">
              <GraduationCapIcon size={16} />
            </span>
            UniACMIS
          </Link>

          <span className="topbar__spacer" />

          <div className="topbar__actions">
            <ConnectionStatus />
          </div>
        </header>

        {user.must_change_password ? (
          <div className="alert alert--warning" style={{ margin: "16px 16px 0" }}>
            <AlertCircleIcon size={18} />
            <span>
              This account is still using the password it was created with. Change it
              before doing anything else.
            </span>
          </div>
        ) : null}

        <main className="content">{children}</main>
      </div>
    </div>
  );
}
