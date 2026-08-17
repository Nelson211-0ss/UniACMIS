"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { ConnectionStatus } from "@/components/ConnectionStatus";
import { useAuth } from "@/lib/auth";

interface NavItem {
  href: string;
  label: string;
  /** Permission the API requires for the destination, or null for everyone. */
  permission: string | null;
  section: string;
}

const NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", permission: null, section: "Overview" },
  {
    href: "/students",
    label: "Students",
    permission: "registry.view_student",
    section: "Registry",
  },
  {
    href: "/students/new",
    label: "Admit a student",
    permission: "registry.add_student",
    section: "Registry",
  },
  {
    href: "/outbox",
    label: "Offline queue",
    permission: null,
    section: "Device",
  },
];

export default function AppLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { user, loading, signOut, can } = useAuth();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  if (loading || !user) {
    return (
      <main className="login">
        <div className="login__card">
          <p className="login__sub">Loading…</p>
        </div>
      </main>
    );
  }

  // Navigation is filtered by permission for usability. The API is the actual
  // boundary — a hidden link is not a security control.
  const visible = NAV.filter((item) => !item.permission || can(item.permission));
  const sections = [...new Set(visible.map((item) => item.section))];

  return (
    <div className="app">
      <header className="topbar">
        <span className="topbar__brand">UniACMIS</span>
        <ConnectionStatus />
        <span className="topbar__user">
          {user.full_name} · {user.roles.join(", ") || "no role"}
        </span>
        <button
          type="button"
          className="secondary"
          onClick={() => void signOut().then(() => router.replace("/login"))}
          style={{ padding: "6px 12px", fontSize: "0.8125rem" }}
        >
          Sign out
        </button>
      </header>

      {user.must_change_password ? (
        <div className="alert alert--warning" style={{ margin: 16, marginBottom: 0 }}>
          This account is still using the password it was created with. Change it
          before doing anything else.
        </div>
      ) : null}

      <div className="shell">
        <nav className="nav" aria-label="Main">
          {sections.map((section) => (
            <div key={section}>
              <div className="nav__section">{section}</div>
              {visible
                .filter((item) => item.section === section)
                .map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    aria-current={pathname === item.href ? "page" : undefined}
                  >
                    {item.label}
                  </Link>
                ))}
            </div>
          ))}
        </nav>

        <main className="content">{children}</main>
      </div>
    </div>
  );
}
