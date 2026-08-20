"use client";

/** Split out from `layout.tsx` on purpose: Next.js's generated route types
 * validate that a `layout.tsx` file only exports the special names it
 * recognises (`default`, `metadata`, ...) — an arbitrary named export like
 * `useStudent` fails that check even though it works fine at runtime. */

import { createContext, useContext } from "react";

export interface StudentIdentity {
  id: number;
  student_id: string;
  full_name: string;
  programme: number;
  programme_code: string;
  programme_name: string;
  curriculum_version: number | null;
  current_level: number;
  status: string;
  photo: string | null;
}

export interface StudentContextValue {
  student: StudentIdentity | null;
  loaded: boolean;
  reload: () => void;
}

export const StudentContext = createContext<StudentContextValue | null>(null);

/** Read the signed-in student's own record from anywhere under `/my/*`,
 * fetched once by the layout rather than by every page that needs it. */
export function useStudent(): StudentContextValue {
  const context = useContext(StudentContext);
  if (!context) {
    throw new Error("useStudent must be used within the student portal (app/(app)/my/layout.tsx)");
  }
  return context;
}
