/**
 * Flushing the outbox.
 *
 * Runs on reconnect, on an interval, and on demand. The important properties:
 *
 * - **Whole batches are retried.** If the connection drops mid-flush, the same
 *   operations are sent again. That is safe because each carries a client-side
 *   UUID the server deduplicates on, so nothing is applied twice.
 * - **One flush at a time.** A second flush racing the first would resend
 *   operations already in flight.
 * - **Backoff on failure**, so a device with no connectivity is not hammering a
 *   dead link every second and draining a battery on solar power.
 */

import { ApiFailure, api } from "@/lib/api";
import * as outbox from "@/lib/outbox";

const MAX_BATCH = 50;
const BASE_BACKOFF_MS = 5_000;
const MAX_BACKOFF_MS = 5 * 60_000;

let flushing = false;
let backoffUntil = 0;

export interface FlushSummary {
  attempted: number;
  applied: number;
  duplicate: number;
  conflict: number;
  rejected: number;
  offline: boolean;
}

const EMPTY: FlushSummary = {
  attempted: 0,
  applied: 0,
  duplicate: 0,
  conflict: 0,
  rejected: 0,
  offline: false,
};

export async function flush(force = false): Promise<FlushSummary> {
  if (flushing) return EMPTY;
  if (!force && Date.now() < backoffUntil) return EMPTY;
  if (typeof navigator !== "undefined" && !navigator.onLine && !force) return EMPTY;

  const queued = await outbox.pending();
  if (queued.length === 0) return EMPTY;

  flushing = true;
  const batch = queued.slice(0, MAX_BATCH);

  try {
    await Promise.all(
      batch.map((op) => outbox.update(op.clientOpId, { status: "syncing" })),
    );

    const response = await api.syncBatch(
      batch.map((op) => ({
        client_op_id: op.clientOpId,
        entity: op.entity,
        action: op.action,
        payload: op.payload,
        client_timestamp: op.clientTimestamp,
        device_id: op.deviceId,
      })),
    );

    const summary: FlushSummary = { ...EMPTY, attempted: batch.length };

    for (const result of response.results) {
      const queuedOp = batch.find((op) => op.clientOpId === result.client_op_id);
      const attempts = (queuedOp?.attempts ?? 0) + 1;

      switch (result.status) {
        case "applied":
        case "duplicate":
          // `duplicate` means the server already had it — the same success from
          // the client's point of view.
          await outbox.update(result.client_op_id, {
            status: "synced",
            attempts,
            result: result.result,
            lastError: undefined,
          });
          summary[result.status] += 1;
          break;

        case "conflict":
          // Held for a human. Not retried, and not discarded.
          await outbox.update(result.client_op_id, {
            status: "failed",
            attempts,
            lastError:
              result.error?.message ??
              "Held for review by the registry — a conflicting record already exists.",
          });
          summary.conflict += 1;
          break;

        case "rejected":
          await outbox.update(result.client_op_id, {
            status: "failed",
            attempts,
            lastError: result.error?.message ?? "The server rejected this entry.",
          });
          summary.rejected += 1;
          break;
      }
    }

    backoffUntil = 0;
    return summary;
  } catch (error) {
    const offline = error instanceof ApiFailure && error.offline;

    // Back to pending, never lost: the connection failing is not the user's
    // mistake and their typing must survive it.
    for (const op of batch) {
      await outbox.update(op.clientOpId, {
        status: "pending",
        attempts: op.attempts + 1,
        lastError: offline
          ? undefined
          : error instanceof Error
            ? error.message
            : "Sync failed",
      });
    }

    const attempts = Math.max(...batch.map((op) => op.attempts + 1));
    backoffUntil =
      Date.now() + Math.min(BASE_BACKOFF_MS * 2 ** (attempts - 1), MAX_BACKOFF_MS);

    return { ...EMPTY, attempted: batch.length, offline };
  } finally {
    flushing = false;
  }
}

/** Start the background flush loop. Returns a teardown function. */
export function startAutoSync(onFlush?: (summary: FlushSummary) => void): () => void {
  const run = async (force = false) => {
    const summary = await flush(force);
    if (summary.attempted > 0) onFlush?.(summary);
  };

  const onOnline = () => {
    backoffUntil = 0; // the link is back; do not sit out the remaining backoff
    void run(true);
  };

  window.addEventListener("online", onOnline);
  const timer = window.setInterval(() => void run(), 30_000);
  void run();

  return () => {
    window.removeEventListener("online", onOnline);
    window.clearInterval(timer);
  };
}
