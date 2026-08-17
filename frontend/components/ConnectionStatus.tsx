"use client";

import { useEffect, useState } from "react";

import * as outbox from "@/lib/outbox";
import { flush, startAutoSync } from "@/lib/sync";

/**
 * Connection and queue indicator.
 *
 * Always visible, because the single most important thing a user needs to know on
 * this network is whether what they just typed has actually reached the server.
 * A pending count of zero is as informative as a count of nine.
 */
export function ConnectionStatus() {
  const [online, setOnline] = useState(true);
  const [count, setCount] = useState(0);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setOnline(navigator.onLine);

    const refresh = () => void outbox.countPending().then(setCount);
    refresh();

    const unsubscribe = outbox.subscribe(refresh);
    const onOnline = () => setOnline(true);
    const onOffline = () => setOnline(false);

    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    const stopAutoSync = startAutoSync(refresh);

    return () => {
      unsubscribe();
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
      stopAutoSync();
    };
  }, []);

  async function syncNow() {
    setBusy(true);
    try {
      await flush(true);
      setCount(await outbox.countPending());
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span className={`conn ${online ? "" : "conn--offline"}`}>
        <span className="conn__dot" />
        {online ? "Online" : "Offline"}
      </span>

      {count > 0 ? (
        <button
          type="button"
          className="secondary"
          onClick={syncNow}
          disabled={busy || !online}
          style={{ padding: "4px 10px", fontSize: "0.8125rem" }}
          title={
            online
              ? "Send queued entries now"
              : "Queued entries will send automatically when the connection returns"
          }
        >
          {busy ? "Sending…" : `${count} queued`}
        </button>
      ) : null}
    </div>
  );
}
