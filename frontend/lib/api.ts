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

  async bulkImportStudents(file: File, commit: boolean, reason?: string) {
    const body = new FormData();
    body.append("file", file);
    body.append("commit", String(commit));
    if (reason) body.append("reason", reason);

    // A multipart upload, not JSON — `request()` always JSON-encodes its body,
    // so this goes straight through fetch the same way `downloadReport` does,
    // letting the browser set the multipart Content-Type (with its boundary)
    // itself rather than us guessing it.
    const response = await fetch(`${BASE_URL}/registry/students/bulk-import/`, {
      method: "POST",
      headers: tokens.access ? { Authorization: `Bearer ${tokens.access}` } : {},
      body,
    });
    if (!response.ok) {
      throw new ApiFailure(response.status, await parseError(response));
    }
    return (await response.json()) as {
      total: number;
      valid: number;
      created: number;
      errors: Array<{ row: number; errors: Record<string, string> }>;
    };
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

  // -------------------------------------------------------- staff directory

  staffProfiles(params = "?page_size=200") {
    return request<{
      results: Array<{ id: number; staff_number: string; full_name: string; department_code: string }>;
    }>(`/registry/staff/${params}`);
  },

  classList(courseId: number, semesterId: number) {
    return request<Array<{ registration_id: number; student_id: string; full_name: string; is_repeat: boolean }>>(
      `/enrollment/class-list/?course=${courseId}&semester=${semesterId}`,
    );
  },

  // ------------------------------------------------------ timetabling (staff)

  timetableRooms(params = "?page_size=200") {
    return request<{
      results: Array<{ id: number; code: string; name: string; building: string; capacity: number; is_active: boolean }>;
    }>(`/timetabling/rooms/${params}`);
  },

  createTimetableRoom(body: { code: string; name: string; building?: string; capacity: number; is_active?: boolean }) {
    return request<{ id: number }>("/timetabling/rooms/", { method: "POST", body });
  },

  updateTimetableRoom(id: number, body: Partial<{ code: string; name: string; building: string; capacity: number; is_active: boolean }>) {
    return request<{ id: number }>(`/timetabling/rooms/${id}/`, { method: "PATCH", body });
  },

  timetableEntries(semesterId: number) {
    return request<{
      results: Array<{
        id: number;
        course: number;
        course_code: string;
        course_title: string;
        semester: number;
        room: number | null;
        room_code: string;
        lecturer: number | null;
        lecturer_name: string;
        day_of_week: number;
        day_of_week_display: string;
        start_time: string;
        end_time: string;
        is_published: boolean;
        published_at: string | null;
      }>;
    }>(`/timetabling/entries/?semester=${semesterId}&page_size=200`);
  },

  createTimetableEntry(body: {
    course: number;
    semester: number;
    room?: number | null;
    lecturer?: number | null;
    day_of_week: number;
    start_time: string;
    end_time: string;
  }) {
    return request<{ id: number }>("/timetabling/entries/", { method: "POST", body });
  },

  updateTimetableEntry(
    id: number,
    body: Partial<{
      course: number;
      semester: number;
      room: number | null;
      lecturer: number | null;
      day_of_week: number;
      start_time: string;
      end_time: string;
    }>,
  ) {
    return request<{ id: number }>(`/timetabling/entries/${id}/`, { method: "PATCH", body });
  },

  publishTimetable(semesterId: number) {
    return request<{ published_count: number }>("/timetabling/entries/publish/", {
      method: "POST",
      body: { semester: semesterId },
    });
  },

  examTimetableEntries(semesterId: number) {
    return request<{
      results: Array<{
        id: number;
        course: number;
        course_code: string;
        course_title: string;
        semester: number;
        room: number | null;
        room_code: string;
        invigilators: number[];
        invigilator_names: string[];
        exam_date: string;
        start_time: string;
        end_time: string;
        is_published: boolean;
        published_at: string | null;
      }>;
    }>(`/timetabling/exam-entries/?semester=${semesterId}&page_size=200`);
  },

  createExamTimetableEntry(body: {
    course: number;
    semester: number;
    room?: number | null;
    invigilators?: number[];
    exam_date: string;
    start_time: string;
    end_time: string;
  }) {
    return request<{ id: number }>("/timetabling/exam-entries/", { method: "POST", body });
  },

  updateExamTimetableEntry(
    id: number,
    body: Partial<{
      course: number;
      semester: number;
      room: number | null;
      invigilators: number[];
      exam_date: string;
      start_time: string;
      end_time: string;
    }>,
  ) {
    return request<{ id: number }>(`/timetabling/exam-entries/${id}/`, { method: "PATCH", body });
  },

  publishExamTimetable(semesterId: number) {
    return request<{ published_count: number }>("/timetabling/exam-entries/publish/", {
      method: "POST",
      body: { semester: semesterId },
    });
  },

  // -------------------------------------------------------- attendance (staff)

  sessionRecords(timetableEntryId: number, sessionDate: string) {
    return request<{
      results: Array<{
        id: number;
        timetable_entry: number;
        registration: number;
        student_id: string;
        student_name: string;
        course_code: string;
        session_date: string;
        status: string;
        notes: string;
      }>;
    }>(`/attendance/records/?timetable_entry=${timetableEntryId}&session_date=${sessionDate}&page_size=200`);
  },

  recordAttendance(
    timetableEntryId: number,
    sessionDate: string,
    marks: Array<{ registration_id: number; status: string; notes?: string }>,
  ) {
    return request<Array<{ id: number; registration: number; status: string }>>("/attendance/records/record/", {
      method: "POST",
      body: { timetable_entry: timetableEntryId, session_date: sessionDate, marks },
    });
  },

  grantWaiver(registrationId: number, reason: string) {
    return request<{
      sessions_recorded: number;
      sessions_attended: number;
      percentage: string | null;
      threshold: string;
      below_threshold: boolean;
      waived: boolean;
      eligible: boolean;
    }>(`/attendance/registrations/${registrationId}/waive/`, { method: "POST", body: { reason } });
  },

  // ------------------------------------------------------ examinations (staff)

  assessments(courseId: number) {
    return request<{
      results: Array<{
        id: number;
        course: number;
        course_code: string;
        name: string;
        weight_percent: string;
        max_score: string;
        sequence: number;
        grade_entry_deadline: string | null;
      }>;
    }>(`/examinations/assessments/?course=${courseId}&page_size=100`);
  },

  createAssessment(body: {
    course: number;
    name: string;
    weight_percent: string | number;
    max_score?: string | number;
    sequence?: number;
    grade_entry_deadline?: string | null;
  }) {
    return request<{ id: number }>("/examinations/assessments/", { method: "POST", body });
  },

  marksForAssessment(assessmentId: number) {
    return request<{
      results: Array<{
        id: number;
        registration: number;
        student_id: string;
        student_name: string;
        assessment: number;
        assessment_name: string;
        score: string;
        effective_score: string;
        is_late: boolean;
        moderated_score: string | null;
        moderation_notes: string;
        is_irregular: boolean;
        irregularity_notes: string;
      }>;
    }>(`/examinations/marks/?assessment=${assessmentId}&page_size=200`);
  },

  recordMark(registrationId: number, assessmentId: number, score: string | number) {
    return request<{ id: number }>("/examinations/marks/record/", {
      method: "POST",
      body: { registration: registrationId, assessment: assessmentId, score },
    });
  },

  moderateMark(markId: number, moderatedScore: string | number, notes: string) {
    return request<{ id: number }>(`/examinations/marks/${markId}/moderate/`, {
      method: "POST",
      body: { moderated_score: moderatedScore, notes },
    });
  },

  flagIrregularity(markId: number, notes: string) {
    return request<{ id: number }>(`/examinations/marks/${markId}/flag-irregularity/`, {
      method: "POST",
      body: { notes },
    });
  },

  clearIrregularity(markId: number) {
    return request<{ id: number }>(`/examinations/marks/${markId}/clear-irregularity/`, { method: "POST" });
  },

  missingMarks(courseId: number, semesterId: number) {
    return request<Array<{ registration_id: number; assessment_id: number; assessment_name: string }>>(
      `/examinations/missing-marks/?course=${courseId}&semester=${semesterId}`,
    );
  },

  gradeAppeals(params = "?page_size=100") {
    return request<{
      results: Array<{
        id: number;
        registration: number;
        student_id: string;
        assessment: number | null;
        reason: string;
        status: string;
        decision_notes: string;
        decided_at: string | null;
        created_at: string;
      }>;
    }>(`/examinations/appeals/${params}`);
  },

  decideAppeal(appealId: number, decision: "upheld" | "rejected", notes: string) {
    return request<{ id: number; status: string }>(`/examinations/appeals/${appealId}/decide/`, {
      method: "POST",
      body: { decision, notes },
    });
  },

  resultApprovals(params = "?page_size=100") {
    return request<{
      results: Array<{
        id: number;
        semester: number;
        programme: number | null;
        status: string;
        approved_by: number | null;
        approved_at: string | null;
        approval_notes: string;
        published_by: number | null;
        published_at: string | null;
        created_at: string;
      }>;
    }>(`/examinations/approvals/${params}`);
  },

  submitForApproval(semesterId: number, programmeId?: number | null) {
    return request<{ id: number }>("/examinations/approvals/", {
      method: "POST",
      body: { semester: semesterId, programme: programmeId ?? null },
    });
  },

  approveResult(approvalId: number, notes?: string) {
    return request<{ id: number; status: string }>(`/examinations/approvals/${approvalId}/approve/`, {
      method: "POST",
      body: { notes: notes ?? "" },
    });
  },

  rejectResult(approvalId: number, notes: string) {
    return request<{ id: number; status: string }>(`/examinations/approvals/${approvalId}/reject/`, {
      method: "POST",
      body: { notes },
    });
  },

  publishResult(approvalId: number) {
    return request<{ id: number; status: string }>(`/examinations/approvals/${approvalId}/publish/`, {
      method: "POST",
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
    return request<{ student_id: number; balance: string; currency: string }>(
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

  // ------------------------------------------------------------- admissions

  applications(params = "?page_size=100") {
    return request<{
      count: number;
      results: Array<{
        id: number;
        reference_number: string;
        full_name: string;
        programme: number;
        programme_code: string;
        status: string;
        score: string | null;
        fee_paid: boolean;
        created_at: string;
      }>;
    }>(`/admissions/applications/${params}`);
  },

  application(id: number) {
    return request<ApplicationDetail>(`/admissions/applications/${id}/`);
  },

  createApplication(body: Record<string, unknown>) {
    return request<ApplicationDetail>("/admissions/applications/", { method: "POST", body });
  },

  submitApplication(id: number) {
    return request<ApplicationDetail>(`/admissions/applications/${id}/submit/`, { method: "POST" });
  },

  withdrawApplication(id: number, reason: string) {
    return request<ApplicationDetail>(`/admissions/applications/${id}/withdraw/`, {
      method: "POST",
      body: { reason },
    });
  },

  reviewApplication(id: number, score: string | number, comments: string) {
    return request<ApplicationDetail>(`/admissions/applications/${id}/review/`, {
      method: "POST",
      body: { score, comments },
    });
  },

  decideApplication(id: number, decision: "offered" | "rejected", reason: string) {
    return request<ApplicationDetail>(`/admissions/applications/${id}/decide/`, {
      method: "POST",
      body: { decision, reason },
    });
  },

  convertApplication(id: number) {
    return request<{ student_id: string; id: number }>(
      `/admissions/applications/${id}/convert/`,
      { method: "POST" },
    );
  },

  initiateApplicationFee(id: number, amount: string | number, currency = "SSP") {
    return request<{ reference: string; status: string }>(
      `/admissions/applications/${id}/initiate-payment/`,
      { method: "POST", body: { amount, currency } },
    );
  },

  confirmApplicationFee(id: number, reference: string) {
    return request<{ reference: string; status: string }>(
      `/admissions/applications/${id}/confirm-payment/`,
      { method: "POST", body: { reference } },
    );
  },

  meritList(programmeId: number, academicYearId: number) {
    return request<
      Array<{
        application_id: number;
        reference_number: string;
        full_name: string;
        rank: number;
        score: string | null;
        admitted: boolean;
        quota_category: string | null;
      }>
    >(`/admissions/merit-list/?programme=${programmeId}&academic_year=${academicYearId}`);
  },

  // ------------------------------------------------------------- curriculum

  faculties(params = "?page_size=100") {
    return request<{
      results: Array<{ id: number; code: string; name: string; is_active: boolean }>;
    }>(`/curriculum/faculties/${params}`);
  },

  createFaculty(body: { institution: number; code: string; name: string; description?: string }) {
    return request<{ id: number }>("/curriculum/faculties/", { method: "POST", body });
  },

  departments(params = "?page_size=100") {
    return request<{
      results: Array<{
        id: number;
        code: string;
        name: string;
        faculty: number;
        is_active: boolean;
      }>;
    }>(`/curriculum/departments/${params}`);
  },

  createDepartment(body: { faculty: number; code: string; name: string; description?: string }) {
    return request<{ id: number }>("/curriculum/departments/", { method: "POST", body });
  },

  programmesDetailed(params = "?page_size=100") {
    return request<{
      results: Array<{
        id: number;
        code: string;
        name: string;
        award: string;
        department: number;
        department_name: string;
        faculty_code: string;
        duration_years: number;
        total_credits_required: number;
        min_credits_per_semester: number;
        max_credits_per_semester: number;
        is_active: boolean;
      }>;
    }>(`/curriculum/programmes/${params}`);
  },

  createProgramme(body: {
    department: number;
    code: string;
    name: string;
    award: string;
    duration_years: number;
    total_credits_required?: number;
    min_credits_per_semester?: number;
    max_credits_per_semester?: number;
  }) {
    return request<{ id: number }>("/curriculum/programmes/", { method: "POST", body });
  },

  createCourse(body: {
    department: number;
    code: string;
    title: string;
    credit_hours: number;
    level?: number;
    contact_hours_per_week?: number;
  }) {
    return request<{ id: number }>("/curriculum/courses/", { method: "POST", body });
  },

  curriculumVersions(params = "?page_size=100") {
    return request<{
      results: Array<{
        id: number;
        programme: number;
        programme_code: string;
        version: string;
        status: string;
        effective_from: number;
        effective_to: number | null;
        core_credits: number;
      }>;
    }>(`/curriculum/curriculum-versions/${params}`);
  },

  createCurriculumVersion(body: {
    programme: number;
    version: string;
    status?: string;
    effective_from: number;
    notes?: string;
  }) {
    return request<{ id: number }>("/curriculum/curriculum-versions/", { method: "POST", body });
  },

  curriculumCourses(versionId: number) {
    return request<{
      results: Array<{
        id: number;
        curriculum_version: number;
        course: number;
        course_code: string;
        course_title: string;
        credit_hours: number;
        year_of_study: number;
        semester_sequence: number;
        is_core: boolean;
        elective_group: string;
      }>;
    }>(`/curriculum/curriculum-courses/?curriculum_version=${versionId}&page_size=200`);
  },

  addCurriculumCourse(body: {
    curriculum_version: number;
    course: number;
    year_of_study: number;
    semester_sequence: number;
    is_core: boolean;
    elective_group?: string;
  }) {
    return request<{ id: number }>("/curriculum/curriculum-courses/", { method: "POST", body });
  },

  removeCurriculumCourse(id: number) {
    return request<void>(`/curriculum/curriculum-courses/${id}/`, { method: "DELETE" });
  },

  prerequisites(courseId?: number) {
    const query = courseId ? `?course=${courseId}&page_size=200` : "?page_size=200";
    return request<{
      results: Array<{
        id: number;
        course: number;
        required_course: number;
        required_course_code: string;
        minimum_grade_point: string | null;
        is_concurrent_allowed: boolean;
      }>;
    }>(`/curriculum/prerequisites/${query}`);
  },

  addPrerequisite(body: {
    course: number;
    required_course: number;
    minimum_grade_point?: string | null;
    is_concurrent_allowed?: boolean;
  }) {
    return request<{ id: number }>("/curriculum/prerequisites/", { method: "POST", body });
  },

  removePrerequisite(id: number) {
    return request<void>(`/curriculum/prerequisites/${id}/`, { method: "DELETE" });
  },

  // -------------------------------------------------------------- academics

  // `InstitutionViewSet` sets `pagination_class = None` (it is a singleton), so
  // this list response is a bare array rather than the usual `{results: [...]}`.
  institution() {
    return request<
      Array<{
        id: number;
        name: string;
        short_name: string;
        mohest_code: string;
        default_currency: string;
        secondary_currency: string;
        address: string;
        phone: string;
        email: string;
        website: string;
        attendance_threshold_percent: string;
        timezone: string;
      }>
    >("/academics/institution/");
  },

  updateInstitution(id: number, body: Record<string, unknown>) {
    return request<{ id: number }>(`/academics/institution/${id}/`, { method: "PATCH", body });
  },

  createAcademicYear(body: {
    name: string;
    start_date: string;
    end_date: string;
    is_current?: boolean;
  }) {
    return request<{ id: number }>("/academics/academic-years/", { method: "POST", body });
  },

  updateAcademicYear(id: number, body: Record<string, unknown>) {
    return request<{ id: number }>(`/academics/academic-years/${id}/`, { method: "PATCH", body });
  },

  createSemester(body: {
    academic_year: number;
    sequence: number;
    name: string;
    teaching_start: string;
    teaching_end: string;
    exam_start?: string | null;
    exam_end?: string | null;
    registration_opens?: string | null;
    registration_closes?: string | null;
    add_drop_closes?: string | null;
    is_current?: boolean;
  }) {
    return request<{ id: number }>("/academics/semesters/", { method: "POST", body });
  },

  updateSemester(id: number, body: Record<string, unknown>) {
    return request<{ id: number }>(`/academics/semesters/${id}/`, { method: "PATCH", body });
  },

  gradingScales() {
    return request<{
      results: Array<{
        id: number;
        name: string;
        description: string;
        max_grade_point: string;
        pass_grade_point: string;
        is_default: boolean;
        is_locked: boolean;
        effective_from: number | null;
        bands: Array<{
          id: number;
          scale: number;
          letter: string;
          min_percent: string;
          max_percent: string;
          grade_point: string;
          is_pass: boolean;
          description: string;
        }>;
      }>;
    }>("/academics/grading-scales/?page_size=50");
  },

  bandsCheck(scaleId: number) {
    return request<{ ok: boolean; errors: string[] }>(
      `/academics/grading-scales/${scaleId}/bands-check/`,
    );
  },

  addGradeBand(body: {
    scale: number;
    letter: string;
    min_percent: string;
    max_percent: string;
    grade_point: string;
    is_pass: boolean;
    description?: string;
  }) {
    return request<{ id: number }>("/academics/grade-bands/", { method: "POST", body });
  },

  removeGradeBand(id: number) {
    return request<void>(`/academics/grade-bands/${id}/`, { method: "DELETE" });
  },

  // ------------------------------------------------------- users and roles

  users(params = "?page_size=100") {
    return request<{
      count: number;
      results: Array<{
        id: number;
        email: string;
        first_name: string;
        last_name: string;
        full_name: string;
        phone: string;
        is_active: boolean;
        is_staff: boolean;
        mfa_enabled: boolean;
        must_change_password: boolean;
        roles: string[];
        last_login: string | null;
      }>;
    }>(`/auth/users/${params}`);
  },

  roles() {
    return request<Array<{ code: string; name: string; description: string }>>("/auth/roles/");
  },

  createUser(body: {
    email: string;
    first_name: string;
    last_name: string;
    middle_name?: string;
    phone?: string;
    password: string;
  }) {
    return request<{ id: number }>("/auth/users/", { method: "POST", body });
  },

  updateUser(id: number, body: Record<string, unknown>) {
    return request<{ id: number }>(`/auth/users/${id}/`, { method: "PATCH", body });
  },

  grantRole(userId: number, roleCode: string, reason: string) {
    return request<{ id: number }>(`/auth/users/${userId}/grant-role/`, {
      method: "POST",
      body: { role_code: roleCode, reason },
    });
  },

  revokeRole(userId: number, roleCode: string, reason: string) {
    return request<void>(`/auth/users/${userId}/revoke-role/`, {
      method: "POST",
      body: { role_code: roleCode, reason },
    });
  },

  roleHistory(userId: number) {
    return request<
      Array<{
        id: number;
        role_code: string;
        granted_at: string;
        granted_by_name: string;
        revoked_at: string | null;
        reason: string;
      }>
    >(`/auth/users/${userId}/role-history/`);
  },

  // ------------------------------------------------------------ audit trail

  auditEntries(params = "") {
    return request<{
      next: string | null;
      previous: string | null;
      results: Array<{
        id: number;
        entity: string;
        object_id: string;
        object_repr: string;
        action: string;
        field_name: string;
        old_value: string | null;
        new_value: string | null;
        description: string;
        reason: string;
        actor_display: string;
        actor_role: string;
        ip_address: string | null;
        request_id: string;
        created_at: string;
      }>;
    }>(`/audit/entries/${params}`);
  },

  verifyAuditChain(limit?: number) {
    const query = limit ? `?limit=${limit}` : "";
    return request<{
      ok: boolean;
      checked: number;
      first_broken_id: number | null;
      detail: string;
    }>(`/audit/verify-chain/${query}`);
  },
};

export interface ApplicationDetail {
  id: number;
  reference_number: string;
  full_name: string;
  programme: number;
  programme_code: string;
  intended_academic_year: number;
  first_name: string;
  middle_name: string;
  last_name: string;
  date_of_birth: string | null;
  gender: string;
  nationality: string;
  phone: string;
  email: string;
  national_id_number: string;
  state_of_origin: string;
  county: string;
  has_disability: boolean;
  disability_details: string;
  physical_address: string;
  previous_institution: string;
  previous_qualification: string;
  previous_grade: string;
  status: string;
  source: string;
  submitted_at: string | null;
  score: string | null;
  decision_reason: string;
  fee_paid: boolean;
  student: number | null;
  documents: Array<{ id: number; document_type: string; title: string; file: string }>;
  reviews: Array<{
    id: number;
    reviewer_name: string;
    score: string;
    comments: string;
    created_at: string;
  }>;
  fee_payments: Array<{
    id: number;
    reference: string;
    amount: string;
    currency: string;
    status: string;
  }>;
  created_at: string;
}

export { BASE_URL };
