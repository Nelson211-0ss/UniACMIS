import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { AuthProvider } from "@/lib/auth";
import { ThemeProvider } from "@/lib/theme";
import { ServiceWorkerRegistrar } from "@/components/ServiceWorkerRegistrar";
import { ThemeToggle } from "@/components/ThemeToggle";

import "./globals.css";

// Runs before first paint so the page never flashes the wrong theme —
// `ThemeProvider` only has to bring React's own state back in sync with
// whatever this already put on the page.
//
// The storage key is repeated as a literal rather than imported from
// `lib/theme.tsx` (kept in sync with its `THEME_STORAGE_KEY` by hand): that
// module is `"use client"`, and this file is a server component, so a
// plain constant crossing that boundary at module-eval time comes through
// as `undefined` rather than its real value — the RSC bundler only knows
// how to build a client reference for a *component* export.
const NO_FLASH_THEME_SCRIPT = `
(function () {
  try {
    var stored = localStorage.getItem("uniacmis.theme");
    var theme = stored === "dark" || stored === "light"
      ? stored
      : (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.setAttribute("data-theme", theme);
  } catch (e) {}
})();
`;

export const metadata: Metadata = {
  title: "UniACMIS",
  description:
    "University Academic Management Information System — works during power and network outages.",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icon.svg" },
  applicationName: "UniACMIS",
};

export const viewport: Viewport = {
  themeColor: "#002045",
  width: "device-width",
  initialScale: 1,
  // Deliberately zoomable: pinch-zoom is how people read dense tables on a
  // 5-inch screen, and disabling it would fail NFR-USE-02.
  maximumScale: 5,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* eslint-disable-next-line @next/next/no-sync-scripts */}
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH_THEME_SCRIPT }} />
      </head>
      <body>
        <ThemeProvider>
          <AuthProvider>
            <ServiceWorkerRegistrar />
            {children}
            <ThemeToggle />
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
