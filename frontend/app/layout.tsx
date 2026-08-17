import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { AuthProvider } from "@/lib/auth";
import { ServiceWorkerRegistrar } from "@/components/ServiceWorkerRegistrar";

import "./globals.css";

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
    <html lang="en">
      <body>
        <AuthProvider>
          <ServiceWorkerRegistrar />
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}
