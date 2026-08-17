"use client";

import { useEffect } from "react";

/**
 * Registers the service worker.
 *
 * Only in production builds: in development the dev server rewrites assets on
 * every change, and a caching worker in front of that produces confusing stale
 * pages that look like application bugs.
 */
export function ServiceWorkerRegistrar() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") return;
    if (!("serviceWorker" in navigator)) return;

    const register = () => {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch((error) => {
        // Not fatal: the app still works online without it. Only offline
        // capability is lost, and that has to be visible rather than silent.
        console.error("Service worker registration failed:", error);
      });
    };

    if (document.readyState === "complete") {
      register();
    } else {
      window.addEventListener("load", register, { once: true });
    }
  }, []);

  return null;
}
