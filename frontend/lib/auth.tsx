"use client";

/**
 * Authentication context.
 *
 * The cached identity is what lets the shell render while offline — the service
 * worker serves the app shell, and this supplies the user's name and roles from
 * localStorage without a round trip.
 *
 * Roles here drive *navigation only*. Every permission decision is made by the
 * server on each request; hiding a link is a courtesy, not a control.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { ApiFailure, api, tokens, type Me } from "@/lib/api";

const CACHED_USER = "uniacmis.user";

interface AuthState {
  user: Me | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  can: (permission: string) => boolean;
  hasRole: (...roles: string[]) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

function readCachedUser(): Me | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(CACHED_USER);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Me;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const cached = readCachedUser();
    if (cached) setUser(cached);

    if (!tokens.access) {
      setLoading(false);
      return;
    }

    // Refresh the identity in the background; a failure to reach the server must
    // not sign a working offline session out.
    api
      .me()
      .then((fresh) => {
        setUser(fresh);
        localStorage.setItem(CACHED_USER, JSON.stringify(fresh));
      })
      .catch((error) => {
        if (error instanceof ApiFailure && !error.offline) {
          tokens.clear();
          localStorage.removeItem(CACHED_USER);
          setUser(null);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const signedIn = await api.login(email, password);
    const full = await api.me();
    setUser(full);
    localStorage.setItem(CACHED_USER, JSON.stringify(full));
    return void signedIn;
  }, []);

  const signOut = useCallback(async () => {
    await api.logout();
    localStorage.removeItem(CACHED_USER);
    setUser(null);
  }, []);

  const can = useCallback(
    (permission: string) => Boolean(user?.permissions?.includes(permission)),
    [user],
  );

  const hasRole = useCallback(
    (...roles: string[]) => Boolean(user?.roles?.some((role) => roles.includes(role))),
    [user],
  );

  const value = useMemo(
    () => ({ user, loading, signIn, signOut, can, hasRole }),
    [user, loading, signIn, signOut, can, hasRole],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return context;
}
