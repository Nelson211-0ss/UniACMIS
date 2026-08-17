/**
 * The offline outbox (NFR-AVAIL-01).
 *
 * A write the user makes with no connection goes here, in IndexedDB, and is
 * flushed later. Three properties matter, and each is a decision rather than an
 * implementation detail:
 *
 * 1. **Durable.** IndexedDB, not memory or sessionStorage — the browser will be
 *    closed, and the laptop will lose power mid-shift.
 * 2. **Identified on the client.** Each operation carries a UUID generated here.
 *    That is what makes a retried flush idempotent on the server, so a dropped
 *    connection cannot produce two student records.
 * 3. **Never silently dropped.** A failed operation stays queued with its error
 *    recorded. Nothing disappears without the user being shown why.
 */

import { openDB, type DBSchema, type IDBPDatabase } from "idb";

export type OutboxStatus = "pending" | "syncing" | "failed" | "synced";

export interface OutboxOperation {
  clientOpId: string;
  entity: string;
  action: "create" | "update" | "delete";
  payload: Record<string, unknown>;
  clientTimestamp: string;
  deviceId: string;
  status: OutboxStatus;
  attempts: number;
  lastError?: string;
  /** Server result once applied, so the UI can show the issued student ID. */
  result?: Record<string, unknown>;
  label: string;
  createdAt: number;
}

interface OutboxSchema extends DBSchema {
  operations: {
    key: string;
    value: OutboxOperation;
    indexes: { "by-status": OutboxStatus; "by-created": number };
  };
}

const DB_NAME = "uniacmis-outbox";
const DB_VERSION = 1;
const STORE = "operations";

let dbPromise: Promise<IDBPDatabase<OutboxSchema>> | null = null;

function getDB() {
  if (!dbPromise) {
    dbPromise = openDB<OutboxSchema>(DB_NAME, DB_VERSION, {
      upgrade(db) {
        const store = db.createObjectStore(STORE, { keyPath: "clientOpId" });
        store.createIndex("by-status", "status");
        store.createIndex("by-created", "createdAt");
      },
    });
  }
  return dbPromise;
}

/** Stable per-browser identifier, so a bad device can be traced in the ledger. */
export function deviceId(): string {
  const KEY = "uniacmis.device-id";
  let id = localStorage.getItem(KEY);
  if (!id) {
    id = `web-${crypto.randomUUID().slice(0, 8)}`;
    localStorage.setItem(KEY, id);
  }
  return id;
}

export async function enqueue(
  entity: string,
  action: OutboxOperation["action"],
  payload: Record<string, unknown>,
  label: string,
): Promise<OutboxOperation> {
  const operation: OutboxOperation = {
    // Generated here, not on the server: this id is what makes a replay safe.
    clientOpId: crypto.randomUUID(),
    entity,
    action,
    payload,
    clientTimestamp: new Date().toISOString(),
    deviceId: deviceId(),
    status: "pending",
    attempts: 0,
    label,
    createdAt: Date.now(),
  };

  const db = await getDB();
  await db.put(STORE, operation);
  notify();
  return operation;
}

export async function all(): Promise<OutboxOperation[]> {
  const db = await getDB();
  const operations = await db.getAll(STORE);
  return operations.sort((a, b) => a.createdAt - b.createdAt);
}

export async function pending(): Promise<OutboxOperation[]> {
  const operations = await all();
  // Oldest first: the order the user entered them is the order they land.
  return operations.filter((op) => op.status === "pending" || op.status === "failed");
}

export async function countPending(): Promise<number> {
  return (await pending()).length;
}

export async function update(
  clientOpId: string,
  changes: Partial<OutboxOperation>,
): Promise<void> {
  const db = await getDB();
  const existing = await db.get(STORE, clientOpId);
  if (!existing) return;
  await db.put(STORE, { ...existing, ...changes });
  notify();
}

export async function remove(clientOpId: string): Promise<void> {
  const db = await getDB();
  await db.delete(STORE, clientOpId);
  notify();
}

/** Clear entries the server has confirmed. Failed ones are kept deliberately. */
export async function clearSynced(): Promise<number> {
  const operations = await all();
  const db = await getDB();
  let removed = 0;
  for (const op of operations) {
    if (op.status === "synced") {
      await db.delete(STORE, op.clientOpId);
      removed += 1;
    }
  }
  notify();
  return removed;
}

// ------------------------------------------------------------- subscriptions

type Listener = () => void;
const listeners = new Set<Listener>();

export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function notify() {
  listeners.forEach((listener) => listener());
}
