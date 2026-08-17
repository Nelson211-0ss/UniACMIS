/**
 * API client.
 *
 * Handles the two things every call needs on this network: a bearer token that
 * may have just expired, and a connection that may not be there at all. A
 * transport failure is reported as `offline: true` rather than as a generic
 * error, because the caller's response to it is completely different — queue the
 * write instead of showing a failure.
 */

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

const ACCESS_KEY = "uniacmis.access";
const REFRESH_KEY = "uniacmis.refresh";

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  request_id?: string;
}

export class ApiFailure extends Error {
  status: number;
  error: ApiError;
  offline: boolean;

  constructor(status: number, error: ApiError, offline = false) {
    super(error.message);
    this.name = "ApiFailure";
    this.status = status;
    this.error = error;
    this.offline = offline;
  }
}

// ------------------------------------------------------------------- tokens

export const tokens = {
  get access() {
    return typeof window === "undefined" ? null : localStorage.getItem(ACCESS_KEY);
  },
  get refresh() {
    return typeof window === "undefined" ? null : localStorage.getItem(REFRESH_KEY);
  },
  set(access: string, refresh?: string) {
    localStorage.setItem(ACCESS_KEY, access);
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

// ------------------------------------------------------------------ requests

interface RequestOptions {
  method?: string;
  body?: unknown;
  auth?: boolean;
  /** Set false for the refresh call itself, to avoid recursion. */
  retryOn401?: boolean;
}

async function parseError(response: Response): Promise<ApiError> {
  try {
    const data = await response.json();
    if (data?.error) return data.error as ApiError;
    return { code: "error", message: JSON.stringify(data) };
  } catch {
    return { code: "error", message: response.statusText || "Request failed" };
  }
}

async function refreshAccessToken(): Promise<boolean> {
  const refresh = tokens.refresh;
  if (!refresh) return false;

  try {
    const response = await fetch(`${BASE_URL}/auth/refresh/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
    });
    if (!response.ok) {
      tokens.clear();
      return false;
    }
    const data = await response.json();
    // Rotation is on server-side, so a new refresh token comes back too.
    tokens.set(data.access, data.refresh);
    return true;
  } catch {
    // A network failure is not an invalid token — keep it and try again later.
    return false;
  }
}

export async function request<T = unknown>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = "GET", body, auth = true, retryOn401 = true } = options;

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (auth && tokens.access) {
    headers.Authorization = `Bearer ${tokens.access}`;
  }

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    // Distinguished from a server error: the caller queues instead of failing.
    throw new ApiFailure(
      0,
      {
        code: "offline",
        message: "No connection to the server.",
      },
      true,
    );
  }

  if (response.status === 401 && retryOn401 && auth) {
    if (await refreshAccessToken()) {
      return request<T>(path, { ...options, retryOn401: false });
    }
  }

  if (!response.ok) {
    throw new ApiFailure(response.status, await parseError(response));
  }

  if (response.status === 204 || response.status === 205) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

// -------------------------------------------------------------------- calls

export interface Me {
  id: number;
  email: string;
  full_name: string;
  roles: string[];
  permissions: string[];
  must_change_password: boolean;
}

export const api = {
  async login(email: string, password: string) {
    const data = await request<{ access: string; refresh: string; user: Me }>(
      "/auth/login/",
      { method: "POST", body: { email, password }, auth: false },
    );
    tokens.set(data.access, data.refresh);
    return data.user;
  },

  async logout() {
    try {
      await request("/auth/logout/", {
        method: "POST",
        body: { refresh: tokens.refresh },
      });
    } finally {
      // Always clear locally, even if the server could not be reached — the user
      // asked to sign out of a shared machine.
      tokens.clear();
    }
  },

  me() {
    return request<Me>("/auth/me/");
  },

  calendar() {
    return request<{
      configured: boolean;
      registration_open: boolean;
      academic_year: { name: string } | null;
      semester: { name: string } | null;
    }>("/academics/calendar/");
  },

  programmes() {
    return request<{ results: Array<{ id: number; code: string; name: string }> }>(
      "/curriculum/programmes/?page_size=100",
    );
  },

  academicYears() {
    return request<{ results: Array<{ id: number; name: string; is_current: boolean }> }>(
      "/academics/academic-years/?page_size=50",
    );
  },

  students(params = "") {
    return request<{
      count: number;
      results: Array<{
        id: number;
        student_id: string;
        full_name: string;
        programme_code: string;
        current_level: number;
        status: string;
      }>;
    }>(`/registry/students/${params}`);
  },

  syncEntities() {
    return request<{ entities: Record<string, string> }>("/sync/entities/");
  },

  syncBatch(operations: unknown[]) {
    return request<{
      summary: Record<string, number>;
      results: Array<{
        client_op_id: string;
        status: "applied" | "duplicate" | "conflict" | "rejected";
        result?: Record<string, unknown>;
        error?: ApiError;
        conflict_id?: number;
      }>;
    }>("/sync/batch/", { method: "POST", body: { operations } });
  },
};

export { BASE_URL };
