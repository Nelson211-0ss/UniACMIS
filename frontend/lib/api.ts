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
    } catch {
      // Sign-out must always succeed on this device even if the server call
      // didn't: an access token that expired while the tab sat idle makes this
      // 401 (the refresh-and-retry in `request` fails too, since the refresh
      // token is stale by then), and a dropped connection makes it a network
      // error. Either way, the caller only wants to be signed out locally —
      // failing here would strand them on the page with no way to leave it.
    } finally {
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
      add_drop_open: boolean;
      exam_period: boolean;
      academic_year: { id: number; name: string } | null;
      semester: { id: number; name: string; sequence: number; academic_year_name: string } | null;
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

  semesters() {
    return request<{
      results: Array<{ id: number; name: string; sequence: number; academic_year_name: string; is_current: boolean }>;
    }>("/academics/semesters/?page_size=50");
  },

  courses(params = "?page_size=200") {
    return request<{
      results: Array<{ id: number; code: string; title: string; credit_hours: number }>;
    }>(`/curriculum/courses/${params}`);
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

  // ------------------------------------------------------- student portal

  /** The signed-in student's own registry record — scoped to self by the
   * API, so this is always "me", never a lookup by id. */
  async myStudent() {
    const page = await request<{
      results: Array<{ id: number; student_id: string; full_name: string; programme: number; current_level: number; status: string }>;
    }>("/registry/students/?page_size=1");
    const summary = page.results[0];
    if (!summary) return null;
    return request<{
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
    }>(`/registry/students/${summary.id}/`);
  },

  curriculumVersion(id: number) {
    return request<{
      id: number;
      programme: number;
      version: string;
      courses: Array<{
        id: number;
        course: number;
        course_code: string;
        course_title: string;
        credit_hours: number;
        year_of_study: number;
        semester_sequence: number;
        is_core: boolean;
      }>;
    }>(`/curriculum/curriculum-versions/${id}/`);
  },

  myRegistrations(semesterId?: number) {
    const query = semesterId ? `?semester=${semesterId}&page_size=100` : "?page_size=100";
    return request<{
      results: Array<{
        id: number;
        student: number;
        course: number;
        course_code: string;
        course_title: string;
        credit_hours: number;
        semester: number;
        semester_display: string;
        status: string;
        is_repeat: boolean;
        drop_reason: string;
        dropped_at: string | null;
        created_at: string;
      }>;
    }>(`/enrollment/registrations/${query}`);
  },

  registerCourse(studentId: number, courseId: number, semesterId: number) {
    return request<{ id: number; status: string }>("/enrollment/registrations/", {
      method: "POST",
      body: { student: studentId, course: courseId, semester: semesterId },
    });
  },

  dropRegistration(registrationId: number, reason: string) {
    return request<{ id: number; status: string }>(
      `/enrollment/registrations/${registrationId}/drop/`,
      { method: "POST", body: { reason } },
    );
  },

  weeklyTimetable(semesterId: number) {
    return request<{
      results: Array<{
        id: number;
        course_code: string;
        course_title: string;
        room_code: string;
        lecturer_name: string;
        day_of_week: number;
        day_of_week_display: string;
        start_time: string;
        end_time: string;
      }>;
    }>(`/timetabling/entries/?semester=${semesterId}&page_size=100`);
  },

  examTimetable(semesterId: number) {
    return request<{
      results: Array<{
        id: number;
        course_code: string;
        course_title: string;
        room_code: string;
        invigilator_names: string[];
        exam_date: string;
        start_time: string;
        end_time: string;
      }>;
    }>(`/timetabling/exam-entries/?semester=${semesterId}&page_size=100`);
  },

  attendanceSummary(registrationId: number) {
    return request<{ sessions_recorded: number; sessions_attended: number; percentage: string | null }>(
      `/attendance/registrations/${registrationId}/summary/`,
    );
  },

  examEligibility(registrationId: number) {
    return request<{
      sessions_recorded: number;
      sessions_attended: number;
      percentage: string | null;
      threshold: string;
      below_threshold: boolean;
      waived: boolean;
      eligible: boolean;
    }>(`/attendance/registrations/${registrationId}/eligibility/`);
  },

  studentResult(studentId: number, semesterId: number) {
    return request<{
      published: boolean;
      withheld: boolean;
      holds?: Array<{ code: string; message: string }>;
      courses: Array<{
        registration_id: number;
        course_id?: number;
        components: Array<{ assessment: string; weight_percent: string; score: string | null; max_score?: string }>;
        complete: boolean;
        has_irregularity: boolean;
        configuration_error: string | null;
        percent: string | null;
        letter: string | null;
        grade_point: string | null;
        is_pass: boolean | null;
      }>;
      gpa: string | null;
    }>(`/examinations/students/${studentId}/semesters/${semesterId}/result/`);
  },

  myAppeals() {
    return request<{
      results: Array<{
        id: number;
        registration: number;
        assessment: number | null;
        reason: string;
        status: string;
        decision_notes: string;
        decided_at: string | null;
        created_at: string;
      }>;
    }>("/examinations/appeals/?page_size=100");
  },

  submitAppeal(registrationId: number, reason: string, assessmentId?: number) {
    return request<{ id: number; status: string }>("/examinations/appeals/", {
      method: "POST",
      body: { registration: registrationId, assessment: assessmentId ?? null, reason },
    });
  },

  // ------------------------------------------------------------- finance

  invoices(params = "?page_size=50") {
    return request<{
      results: Array<{
        id: number;
        invoice_number: string;
        student: number;
        semester: number;
        amount: string;
        discount_amount: string;
        net_amount: string;
        balance: string;
        currency: string;
        status: string;
        due_date: string;
      }>;
    }>(`/finance/invoices/${params}`);
  },

  generateInvoice(studentId: number, semesterId: number) {
    return request<{ id: number; invoice_number: string; amount: string }>(
      "/finance/invoices/generate/",
      { method: "POST", body: { student: studentId, semester: semesterId } },
    );
  },

  payments(params = "?page_size=50") {
    return request<{
      results: Array<{
        id: number;
        invoice: number;
        method: string;
        amount: string;
        currency: string;
        status: string;
        reference: string;
        receipt_number: string;
        confirmed_at: string | null;
      }>;
    }>(`/finance/payments/${params}`);
  },

  recordPayment(body: { invoice: number; method: string; amount: string; reference: string }) {
    return request<{ id: number; status: string }>("/finance/payments/record/", {
      method: "POST",
      body,
    });
  },

  confirmPayment(paymentId: number) {
    return request<{ id: number; status: string }>(`/finance/payments/${paymentId}/confirm/`, {
      method: "POST",
    });
  },

  myFeeBalance(studentId: number) {
    return request<{ student_id: number; balance: string }>(
      `/finance/students/${studentId}/balance/`,
    );
  },

  defaulterReport() {
    return request<
      Array<{
        invoice_number: string;
        student_number: string;
        student_name: string;
        balance: string;
        currency: string;
        days_overdue: number;
      }>
    >("/finance/reports/defaulters/");
  },

  // ------------------------------------------------------------------- hr

  leaveRequests(params = "?page_size=50") {
    return request<{
      results: Array<{
        id: number;
        staff: number;
        staff_number: string;
        leave_type: string;
        start_date: string;
        end_date: string;
        reason: string;
        status: string;
        decision_notes: string;
        created_at: string;
      }>;
    }>(`/hr/leave-requests/${params}`);
  },

  submitLeaveRequest(body: { leave_type: string; start_date: string; end_date: string; reason: string }) {
    return request<{ id: number; status: string }>("/hr/leave-requests/submit/", {
      method: "POST",
      body,
    });
  },

  endorseLeaveRequest(id: number) {
    return request<{ id: number; status: string }>(`/hr/leave-requests/${id}/endorse/`, {
      method: "POST",
    });
  },

  decideLeaveRequest(id: number, approve: boolean, notes: string) {
    return request<{ id: number; status: string }>(`/hr/leave-requests/${id}/decide/`, {
      method: "POST",
      body: { approve, notes },
    });
  },

  payrollExport() {
    return request<
      Array<{
        staff_id: number;
        staff_number: string;
        staff_name: string;
        position: string;
        contract_type: string;
        basic_salary: string;
        currency: string;
      }>
    >("/hr/payroll-export/");
  },

  appraisals(params = "?page_size=50") {
    return request<{
      results: Array<{
        id: number;
        staff: number;
        staff_number: string;
        academic_year: number;
        rating: number;
        comments: string;
        promotion_recommended: boolean;
      }>;
    }>(`/hr/appraisals/${params}`);
  },

  // -------------------------------------------------------------- library

  libraryItems(params = "?page_size=50") {
    return request<{
      results: Array<{
        id: number;
        title: string;
        author: string;
        item_type: string;
        is_electronic: boolean;
        total_copies: number;
        available_copies: number;
        is_active: boolean;
      }>;
    }>(`/library/items/${params}`);
  },

  createLibraryItem(body: {
    title: string;
    author?: string;
    item_type: string;
    total_copies: number;
    is_electronic?: boolean;
    resource_url?: string;
  }) {
    return request<{ id: number }>("/library/items/", { method: "POST", body });
  },

  loans(params = "?page_size=50") {
    return request<{
      results: Array<{
        id: number;
        item: number;
        item_title: string;
        borrower_student: number | null;
        borrower_staff: number | null;
        borrower_number: string;
        due_date: string;
        returned_at: string | null;
        status: string;
        fine_amount: string;
        owed: string;
        currency: string;
        fine_waived: boolean;
      }>;
    }>(`/library/loans/${params}`);
  },

  checkoutItem(body: { item: number; borrower_student?: number; borrower_staff?: number }) {
    return request<{ id: number; status: string }>("/library/loans/checkout/", {
      method: "POST",
      body,
    });
  },

  returnLoan(loanId: number) {
    return request<{ id: number; status: string }>(`/library/loans/${loanId}/return-loan/`, {
      method: "POST",
    });
  },

  waiveFine(loanId: number, reason: string) {
    return request<{ id: number }>(`/library/loans/${loanId}/waive-fine/`, {
      method: "POST",
      body: { reason },
    });
  },

  // --------------------------------------------------------------- hostel

  rooms(params = "?page_size=100") {
    return request<{
      results: Array<{
        id: number;
        building: string;
        room_number: string;
        capacity: number;
        gender_restriction: string;
        available_beds: number;
        occupied_beds: number;
        is_active: boolean;
      }>;
    }>(`/hostel/rooms/${params}`);
  },

  createRoom(body: { building: string; room_number: string; capacity: number; gender_restriction: string }) {
    return request<{ id: number }>("/hostel/rooms/", { method: "POST", body });
  },

  allocations(params = "?page_size=50") {
    return request<{
      results: Array<{
        id: number;
        student: number;
        student_number: string;
        room: number;
        room_label: string;
        academic_year: number;
        status: string;
        allocated_at: string;
        vacated_at: string | null;
      }>;
    }>(`/hostel/allocations/${params}`);
  },

  allocateRoom(body: { student: number; room: number; academic_year: number }) {
    return request<{ id: number; status: string }>("/hostel/allocations/allocate/", {
      method: "POST",
      body,
    });
  },

  vacateAllocation(id: number, reason?: string) {
    return request<{ id: number; status: string }>(`/hostel/allocations/${id}/vacate/`, {
      method: "POST",
      body: { reason: reason ?? "" },
    });
  },

  // ------------------------------------------------------------- documents

  transcriptRequests(params = "?page_size=50") {
    return request<{
      results: Array<{
        id: number;
        student: number;
        student_number: string;
        reason: string;
        status: string;
        decision_notes: string;
        created_at: string;
      }>;
    }>(`/documents/transcript-requests/${params}`);
  },

  requestTranscript(reason: string, studentId?: number) {
    return request<{ id: number; status: string }>("/documents/transcript-requests/submit/", {
      method: "POST",
      body: studentId ? { student: studentId, reason } : { reason },
    });
  },

  decideTranscriptRequest(id: number, approve: boolean, notes: string) {
    return request<{ id: number; status: string }>(
      `/documents/transcript-requests/${id}/decide/`,
      { method: "POST", body: { approve, notes } },
    );
  },

  issuedDocuments(params = "?page_size=50") {
    return request<{
      results: Array<{
        id: number;
        student: number;
        student_number: string;
        document_type: string;
        serial_number: string;
        issued_at: string;
        is_revoked: boolean;
        is_valid: boolean;
      }>;
    }>(`/documents/issued/${params}`);
  },

  issueCertificate(studentId: number, overrideReason?: string) {
    return request<{ id: number; serial_number: string }>(
      "/documents/issued/issue-certificate/",
      { method: "POST", body: { student: studentId, override_reason: overrideReason ?? "" } },
    );
  },

  revokeDocument(id: number, reason: string) {
    return request<{ id: number }>(`/documents/issued/${id}/revoke/`, {
      method: "POST",
      body: { reason },
    });
  },

  myClearance(studentId: number) {
    return request<{
      clear: boolean;
      holds: Array<{ code: string; message: string; source: string; blocking: boolean }>;
    }>(`/documents/students/${studentId}/clearance/`);
  },

  verifyDocument(serialNumber: string) {
    return request<{
      serial_number: string;
      document_type: string;
      student_name: string;
      issued_at: string;
      is_valid: boolean;
    }>(`/documents/verify/${encodeURIComponent(serialNumber)}/`, { auth: false });
  },

  // -------------------------------------------------------- communications

  announcements(params = "?page_size=50") {
    return request<{
      results: Array<{
        id: number;
        title: string;
        body: string;
        audience_type: string;
        programme: number | null;
        sent_at: string;
        recipient_count: number;
      }>;
    }>(`/communications/announcements/${params}`);
  },

  sendAnnouncement(body: {
    title: string;
    body: string;
    audience_type: string;
    programme?: number;
  }) {
    return request<{ id: number }>("/communications/announcements/send/", {
      method: "POST",
      body,
    });
  },

  // --------------------------------------------------------------- alumni

  alumniProfiles(params = "?page_size=50") {
    return request<{
      results: Array<{
        id: number;
        student: number;
        student_number: string;
        student_name: string;
        current_employer: string;
        current_position: string;
        employment_status: string;
        is_contactable: boolean;
      }>;
    }>(`/alumni/profiles/${params}`);
  },

  createAlumniProfile(body: { student: number; current_employer?: string; employment_status?: string }) {
    return request<{ id: number }>("/alumni/profiles/", { method: "POST", body });
  },

  alumniEvents(params = "?page_size=50") {
    return request<{
      results: Array<{
        id: number;
        title: string;
        description: string;
        event_date: string;
        location: string;
      }>;
    }>(`/alumni/events/${params}`);
  },

  createAlumniEvent(body: { title: string; event_date: string; location?: string; description?: string }) {
    return request<{ id: number }>("/alumni/events/", { method: "POST", body });
  },

  // ------------------------------------------------------------- reporting

  reportingDashboard() {
    return request<
      Array<{ key: string; label: string; data: Record<string, unknown> }>
    >("/reporting/dashboard/");
  },

  passRateReport(courseId: number, semesterId: number) {
    return request<{
      course_id: number;
      semester_id: number;
      passed: number;
      failed: number;
      incomplete: number;
      pass_rate_percent: number | null;
    }>(`/reporting/pass-rate/?course=${courseId}&semester=${semesterId}`);
  },

  /** The export endpoint requires the same bearer token as everything else,
   * so a plain `<a href>` (which sends no Authorization header) cannot be
   * used — this fetches the file with auth and hands the browser a blob to
   * save instead. */
  async downloadReport(key: string, format: "csv" | "xlsx") {
    const response = await fetch(
      `${BASE_URL}/reporting/reports/${key}/export/?export_format=${format}`,
      { headers: tokens.access ? { Authorization: `Bearer ${tokens.access}` } : {} },
    );
    if (!response.ok) {
      throw new ApiFailure(response.status, await parseError(response));
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${key}.${format}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
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
