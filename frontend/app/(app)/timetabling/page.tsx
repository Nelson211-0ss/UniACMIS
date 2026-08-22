"use client";

/** Timetable & rooms (FR-TT-01…04). The registrar owns the room inventory and
 * the class timetable; the examinations office owns the exam timetable —
 * split exactly the way `apps.accounts.roles` grants the two permission
 * sets, never both to the same role. Clash detection lives server-side
 * (`timetabling.services`); this page's job is to submit the entry and show
 * whatever 409 comes back, not to second-guess the check client-side. */

import { useEffect, useState } from "react";

import { BuildingIcon } from "@/components/icons";
import { ApiFailure, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

interface Semester {
  id: number;
  name: string;
  academic_year_name: string;
  is_current: boolean;
}
interface CourseOption {
  id: number;
  code: string;
  title: string;
}
interface RoomOption {
  id: number;
  code: string;
  name: string;
  building: string;
  capacity: number;
  is_active: boolean;
}
interface StaffOption {
  id: number;
  full_name: string;
  staff_number: string;
}

function errorText(error: unknown, fallback: string) {
  return error instanceof ApiFailure ? error.error.message : fallback;
}

export default function TimetablingPage() {
  const { can } = useAuth();
  const canManageRooms = can("timetabling.add_room");
  const canManageEntries = can("timetabling.add_timetableentry");
  const canManageExams = can("timetabling.add_examtimetable");
  const canViewRooms = can("timetabling.view_room");

  const [semesters, setSemesters] = useState<Semester[]>([]);
  const [courses, setCourses] = useState<CourseOption[]>([]);
  const [rooms, setRooms] = useState<RoomOption[]>([]);
  const [staff, setStaff] = useState<StaffOption[]>([]);
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "offline" | "error">("loading");

  async function loadReference() {
    try {
      const [semesterPage, coursePage, roomPage, staffPage] = await Promise.all([
        api.semesters(),
        api.courses(),
        canViewRooms ? api.timetableRooms() : Promise.resolve({ results: [] as RoomOption[] }),
        canManageExams ? api.staffProfiles() : Promise.resolve({ results: [] as StaffOption[] }),
      ]);
      setSemesters(semesterPage.results);
      setCourses(coursePage.results);
      setRooms(roomPage.results);
      setStaff(staffPage.results);
      setState("ready");
    } catch (error) {
      setState(error instanceof ApiFailure && error.offline ? "offline" : "error");
    }
  }

  useEffect(() => {
    void loadReference();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Timetable &amp; rooms</h1>
          <p className="page-subtitle">Room inventory, the class timetable and the exam timetable</p>
        </div>
      </div>

      {notice ? (
        <div className={`alert alert--${notice.kind === "success" ? "success" : "error"}`}>
          <span>{notice.text}</span>
        </div>
      ) : null}
      {state === "offline" ? (
        <div className="alert alert--warning">
          <span>No connection. Showing whatever loaded earlier on this device.</span>
        </div>
      ) : null}
      {state === "error" ? (
        <div className="alert alert--error">
          <span>Could not load timetabling reference data. Try again shortly.</span>
        </div>
      ) : null}

      {canViewRooms ? (
        <RoomsSection rooms={rooms} canManage={canManageRooms} onNotice={setNotice} onReload={loadReference} />
      ) : null}

      {canManageEntries ? (
        <ClassTimetableSection semesters={semesters} courses={courses} rooms={rooms} onNotice={setNotice} />
      ) : null}

      {canManageExams ? (
        <ExamTimetableSection semesters={semesters} courses={courses} rooms={rooms} staff={staff} onNotice={setNotice} />
      ) : null}

      {!canViewRooms && !canManageEntries && !canManageExams ? (
        <div className="card">
          <div className="empty-state">
            <span className="empty-state__title">Nothing to manage here</span>
            <p className="muted">Your role has no timetabling actions.</p>
          </div>
        </div>
      ) : null}
    </>
  );
}

function RoomsSection({
  rooms,
  canManage,
  onNotice,
  onReload,
}: {
  rooms: RoomOption[];
  canManage: boolean;
  onNotice: (n: { kind: "success" | "error"; text: string }) => void;
  onReload: () => void;
}) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [building, setBuilding] = useState("");
  const [capacity, setCapacity] = useState("40");
  const [busy, setBusy] = useState(false);

  async function addRoom() {
    if (!code.trim() || !name.trim()) return;
    setBusy(true);
    try {
      await api.createTimetableRoom({ code, name, building, capacity: Number(capacity) || 1 });
      onNotice({ kind: "success", text: "Room added." });
      setCode("");
      setName("");
      setBuilding("");
      onReload();
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not add the room.") });
    } finally {
      setBusy(false);
    }
  }

  async function toggleActive(room: RoomOption) {
    try {
      await api.updateTimetableRoom(room.id, { is_active: !room.is_active });
      onNotice({ kind: "success", text: `${room.code} marked ${room.is_active ? "inactive" : "active"}.` });
      onReload();
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not update the room.") });
    }
  }

  return (
    <>
      {canManage ? (
        <div className="card">
          <div className="card__header">
            <span className="card__icon">
              <BuildingIcon size={18} />
            </span>
            <h2>Add a room</h2>
          </div>
          <div className="field-row">
            <div className="field" style={{ width: 110 }}>
              <label htmlFor="room-code">Code</label>
              <input id="room-code" value={code} onChange={(event) => setCode(event.target.value)} placeholder="LT1" />
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label htmlFor="room-name">Name</label>
              <input id="room-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="Lecture Theatre 1" />
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label htmlFor="room-building">Building</label>
              <input id="room-building" value={building} onChange={(event) => setBuilding(event.target.value)} />
            </div>
            <div className="field" style={{ width: 100 }}>
              <label htmlFor="room-capacity">Capacity</label>
              <input id="room-capacity" value={capacity} onChange={(event) => setCapacity(event.target.value)} />
            </div>
          </div>
          <button type="button" disabled={busy} onClick={() => void addRoom()}>
            Add room
          </button>
        </div>
      ) : null}

      <div className="section-title">Rooms</div>
      <div className="card">
        {rooms.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__title">No rooms yet</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Room</th>
                  <th>Building</th>
                  <th>Capacity</th>
                  <th>Status</th>
                  {canManage ? <th /> : null}
                </tr>
              </thead>
              <tbody>
                {rooms.map((room) => (
                  <tr key={room.id}>
                    <td className="cell-primary">
                      {room.code} — {room.name}
                    </td>
                    <td>{room.building || "—"}</td>
                    <td>{room.capacity}</td>
                    <td>
                      <span className={`pill ${room.is_active ? "pill--synced" : "pill--failed"}`}>
                        {room.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    {canManage ? (
                      <td>
                        <button type="button" className="sm ghost" onClick={() => void toggleActive(room)}>
                          {room.is_active ? "Deactivate" : "Activate"}
                        </button>
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}

function ClassTimetableSection({
  semesters,
  courses,
  rooms,
  onNotice,
}: {
  semesters: Semester[];
  courses: CourseOption[];
  rooms: RoomOption[];
  onNotice: (n: { kind: "success" | "error"; text: string }) => void;
}) {
  const [semesterId, setSemesterId] = useState<number | "">("");
  const [entries, setEntries] = useState<
    Array<{
      id: number;
      course_code: string;
      course_title: string;
      room_code: string;
      lecturer_name: string;
      day_of_week_display: string;
      start_time: string;
      end_time: string;
      is_published: boolean;
    }>
  >([]);
  const [courseId, setCourseId] = useState<number | "">("");
  const [roomId, setRoomId] = useState<number | "">("");
  const [dayOfWeek, setDayOfWeek] = useState(0);
  const [startTime, setStartTime] = useState("08:00");
  const [endTime, setEndTime] = useState("09:00");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const current = semesters.find((s) => s.is_current);
    if (current) setSemesterId(current.id);
  }, [semesters]);

  async function reload(id: number) {
    const page = await api.timetableEntries(id);
    setEntries(page.results);
  }

  useEffect(() => {
    if (semesterId) void reload(Number(semesterId)).catch(() => setEntries([]));
  }, [semesterId]);

  async function addEntry() {
    if (!semesterId || !courseId) return;
    setBusy(true);
    try {
      await api.createTimetableEntry({
        course: Number(courseId),
        semester: Number(semesterId),
        room: roomId || null,
        day_of_week: dayOfWeek,
        start_time: startTime,
        end_time: endTime,
      });
      onNotice({ kind: "success", text: "Timetable entry added." });
      await reload(Number(semesterId));
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not add the entry — check for a room or lecturer clash.") });
    } finally {
      setBusy(false);
    }
  }

  async function publish() {
    if (!semesterId) return;
    try {
      const result = await api.publishTimetable(Number(semesterId));
      onNotice({ kind: "success", text: `Published ${result.published_count} entr${result.published_count === 1 ? "y" : "ies"}.` });
      await reload(Number(semesterId));
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not publish the timetable.") });
    }
  }

  return (
    <>
      <div className="section-title">Class timetable</div>
      <div className="card">
        <div className="field">
          <label htmlFor="tt-semester">Semester</label>
          <select id="tt-semester" value={semesterId} onChange={(event) => setSemesterId(event.target.value ? Number(event.target.value) : "")}>
            <option value="">Select…</option>
            {semesters.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} · {s.academic_year_name}
              </option>
            ))}
          </select>
        </div>

        <div className="field-row" style={{ marginTop: 8 }}>
          <div className="field" style={{ flex: 2 }}>
            <label htmlFor="tt-course">Course</label>
            <select id="tt-course" value={courseId} onChange={(event) => setCourseId(event.target.value ? Number(event.target.value) : "")}>
              <option value="">Select…</option>
              {courses.map((course) => (
                <option key={course.id} value={course.id}>
                  {course.code} — {course.title}
                </option>
              ))}
            </select>
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label htmlFor="tt-room">Room</label>
            <select id="tt-room" value={roomId} onChange={(event) => setRoomId(event.target.value ? Number(event.target.value) : "")}>
              <option value="">Unassigned</option>
              {rooms.map((room) => (
                <option key={room.id} value={room.id}>
                  {room.code}
                </option>
              ))}
            </select>
          </div>
          <div className="field" style={{ width: 140 }}>
            <label htmlFor="tt-day">Day</label>
            <select id="tt-day" value={dayOfWeek} onChange={(event) => setDayOfWeek(Number(event.target.value))}>
              {DAYS.map((day, index) => (
                <option key={day} value={index}>
                  {day}
                </option>
              ))}
            </select>
          </div>
          <div className="field" style={{ width: 110 }}>
            <label htmlFor="tt-start">Start</label>
            <input id="tt-start" type="time" value={startTime} onChange={(event) => setStartTime(event.target.value)} />
          </div>
          <div className="field" style={{ width: 110 }}>
            <label htmlFor="tt-end">End</label>
            <input id="tt-end" type="time" value={endTime} onChange={(event) => setEndTime(event.target.value)} />
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button type="button" disabled={busy || !semesterId || !courseId} onClick={() => void addEntry()}>
            Add entry
          </button>
          <button type="button" className="secondary" disabled={!semesterId || entries.length === 0} onClick={() => void publish()}>
            Publish semester
          </button>
        </div>
      </div>

      <div className="card">
        {entries.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__title">No entries for this semester yet</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Course</th>
                  <th>Room</th>
                  <th>Lecturer</th>
                  <th>Day</th>
                  <th>Time</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr key={entry.id}>
                    <td className="cell-primary">{entry.course_code}</td>
                    <td>{entry.room_code || "—"}</td>
                    <td>{entry.lecturer_name || "Unassigned"}</td>
                    <td>{entry.day_of_week_display}</td>
                    <td>
                      {entry.start_time}–{entry.end_time}
                    </td>
                    <td>
                      <span className={`pill ${entry.is_published ? "pill--synced" : "pill--pending"}`}>
                        {entry.is_published ? "Published" : "Draft"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}

function ExamTimetableSection({
  semesters,
  courses,
  rooms,
  staff,
  onNotice,
}: {
  semesters: Semester[];
  courses: CourseOption[];
  rooms: RoomOption[];
  staff: StaffOption[];
  onNotice: (n: { kind: "success" | "error"; text: string }) => void;
}) {
  const [semesterId, setSemesterId] = useState<number | "">("");
  const [entries, setEntries] = useState<
    Array<{
      id: number;
      course_code: string;
      course_title: string;
      room_code: string;
      invigilator_names: string[];
      exam_date: string;
      start_time: string;
      end_time: string;
      is_published: boolean;
    }>
  >([]);
  const [courseId, setCourseId] = useState<number | "">("");
  const [roomId, setRoomId] = useState<number | "">("");
  const [invigilatorIds, setInvigilatorIds] = useState<number[]>([]);
  const [examDate, setExamDate] = useState("");
  const [startTime, setStartTime] = useState("09:00");
  const [endTime, setEndTime] = useState("12:00");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const current = semesters.find((s) => s.is_current);
    if (current) setSemesterId(current.id);
  }, [semesters]);

  async function reload(id: number) {
    const page = await api.examTimetableEntries(id);
    setEntries(page.results);
  }

  useEffect(() => {
    if (semesterId) void reload(Number(semesterId)).catch(() => setEntries([]));
  }, [semesterId]);

  async function addEntry() {
    if (!semesterId || !courseId || !examDate) return;
    setBusy(true);
    try {
      await api.createExamTimetableEntry({
        course: Number(courseId),
        semester: Number(semesterId),
        room: roomId || null,
        invigilators: invigilatorIds,
        exam_date: examDate,
        start_time: startTime,
        end_time: endTime,
      });
      onNotice({ kind: "success", text: "Exam entry added." });
      await reload(Number(semesterId));
    } catch (error) {
      onNotice({
        kind: "error",
        text: errorText(error, "Could not add the exam entry — check for a room or invigilator clash, or the exam window."),
      });
    } finally {
      setBusy(false);
    }
  }

  async function publish() {
    if (!semesterId) return;
    try {
      const result = await api.publishExamTimetable(Number(semesterId));
      onNotice({ kind: "success", text: `Published ${result.published_count} entr${result.published_count === 1 ? "y" : "ies"}.` });
      await reload(Number(semesterId));
    } catch (error) {
      onNotice({ kind: "error", text: errorText(error, "Could not publish the exam timetable.") });
    }
  }

  return (
    <>
      <div className="section-title">Exam timetable</div>
      <div className="card">
        <div className="field">
          <label htmlFor="ex-semester">Semester</label>
          <select id="ex-semester" value={semesterId} onChange={(event) => setSemesterId(event.target.value ? Number(event.target.value) : "")}>
            <option value="">Select…</option>
            {semesters.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} · {s.academic_year_name}
              </option>
            ))}
          </select>
        </div>
        <div className="field-row" style={{ marginTop: 8 }}>
          <div className="field" style={{ flex: 2 }}>
            <label htmlFor="ex-course">Course</label>
            <select id="ex-course" value={courseId} onChange={(event) => setCourseId(event.target.value ? Number(event.target.value) : "")}>
              <option value="">Select…</option>
              {courses.map((course) => (
                <option key={course.id} value={course.id}>
                  {course.code} — {course.title}
                </option>
              ))}
            </select>
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label htmlFor="ex-room">Room</label>
            <select id="ex-room" value={roomId} onChange={(event) => setRoomId(event.target.value ? Number(event.target.value) : "")}>
              <option value="">Unassigned</option>
              {rooms.map((room) => (
                <option key={room.id} value={room.id}>
                  {room.code}
                </option>
              ))}
            </select>
          </div>
          <div className="field" style={{ width: 150 }}>
            <label htmlFor="ex-date">Exam date</label>
            <input id="ex-date" type="date" value={examDate} onChange={(event) => setExamDate(event.target.value)} />
          </div>
          <div className="field" style={{ width: 110 }}>
            <label htmlFor="ex-start">Start</label>
            <input id="ex-start" type="time" value={startTime} onChange={(event) => setStartTime(event.target.value)} />
          </div>
          <div className="field" style={{ width: 110 }}>
            <label htmlFor="ex-end">End</label>
            <input id="ex-end" type="time" value={endTime} onChange={(event) => setEndTime(event.target.value)} />
          </div>
        </div>
        <div className="field">
          <label htmlFor="ex-invigilators">Invigilators</label>
          <select
            id="ex-invigilators"
            multiple
            value={invigilatorIds.map(String)}
            onChange={(event) => setInvigilatorIds(Array.from(event.target.selectedOptions).map((option) => Number(option.value)))}
            style={{ height: 90 }}
          >
            {staff.map((member) => (
              <option key={member.id} value={member.id}>
                {member.full_name} ({member.staff_number})
              </option>
            ))}
          </select>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button type="button" disabled={busy || !semesterId || !courseId || !examDate} onClick={() => void addEntry()}>
            Add exam entry
          </button>
          <button type="button" className="secondary" disabled={!semesterId || entries.length === 0} onClick={() => void publish()}>
            Publish semester
          </button>
        </div>
      </div>

      <div className="card">
        {entries.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__title">No exam entries for this semester yet</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Course</th>
                  <th>Room</th>
                  <th>Invigilators</th>
                  <th>Date</th>
                  <th>Time</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr key={entry.id}>
                    <td className="cell-primary">{entry.course_code}</td>
                    <td>{entry.room_code || "—"}</td>
                    <td>{entry.invigilator_names.join(", ") || "—"}</td>
                    <td>{entry.exam_date}</td>
                    <td>
                      {entry.start_time}–{entry.end_time}
                    </td>
                    <td>
                      <span className={`pill ${entry.is_published ? "pill--synced" : "pill--pending"}`}>
                        {entry.is_published ? "Published" : "Draft"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
