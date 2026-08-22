"use client";

/** Hostel (FR-HOS-01…03). A student sees only their own allocation; hostel
 * staff manage the room inventory and allocate/vacate. */

import { useEffect, useState } from "react";

import { BedIcon } from "@/components/icons";
import { ApiFailure, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Room {
  id: number;
  building: string;
  room_number: string;
  capacity: number;
  gender_restriction: string;
  available_beds: number;
  occupied_beds: number;
}

interface Allocation {
  id: number;
  student: number;
  student_number: string;
  room: number;
  room_label: string;
  status: string;
  allocated_at: string;
  vacated_at: string | null;
}

export default function HostelPage() {
  const { can } = useAuth();
  const canViewRooms = can("hostel.view_room");
  const canManageRooms = can("hostel.add_room");
  const canAllocate = can("hostel.add_allocation");
  const canVacate = can("hostel.change_allocation");

  const [rooms, setRooms] = useState<Room[]>([]);
  const [allocations, setAllocations] = useState<Allocation[]>([]);
  const [academicYears, setAcademicYears] = useState<Array<{ id: number; name: string }>>([]);
  const [state, setState] = useState<"loading" | "ready" | "offline" | "error">("loading");
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const [newBuilding, setNewBuilding] = useState("");
  const [newRoomNumber, setNewRoomNumber] = useState("");
  const [newCapacity, setNewCapacity] = useState("2");
  const [newGender, setNewGender] = useState("female");

  const [allocateRoomId, setAllocateRoomId] = useState<number | null>(null);
  const [allocateStudent, setAllocateStudent] = useState("");
  const [allocateYear, setAllocateYear] = useState("");

  async function load() {
    try {
      const [roomPage, allocationPage] = await Promise.all([
        // The room inventory is a staff concern (FR-HOS-01…03) — a student
        // sees only their own allocation below, so this is skipped rather
        // than fetched and 403ing for them.
        canViewRooms ? api.rooms() : Promise.resolve({ results: [] as Room[] }),
        api.allocations(),
      ]);
      setRooms(roomPage.results);
      setAllocations(allocationPage.results);
      if (canAllocate) {
        setAcademicYears((await api.academicYears().catch(() => ({ results: [] }))).results);
      }
      setState("ready");
    } catch (error) {
      setState(error instanceof ApiFailure && error.offline ? "offline" : "error");
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function addRoom() {
    if (!newBuilding.trim() || !newRoomNumber.trim()) return;
    setBusy(true);
    setNotice(null);
    try {
      await api.createRoom({
        building: newBuilding,
        room_number: newRoomNumber,
        capacity: Number(newCapacity) || 1,
        gender_restriction: newGender,
      });
      setNotice({ kind: "success", text: "Room added." });
      setNewBuilding("");
      setNewRoomNumber("");
      await load();
    } catch (error) {
      setNotice({ kind: "error", text: error instanceof ApiFailure ? error.error.message : "Could not add the room." });
    } finally {
      setBusy(false);
    }
  }

  async function allocate() {
    if (!allocateRoomId || !allocateStudent || !allocateYear) return;
    setBusy(true);
    setNotice(null);
    try {
      await api.allocateRoom({ student: Number(allocateStudent), room: allocateRoomId, academic_year: Number(allocateYear) });
      setNotice({ kind: "success", text: "Room allocated." });
      setAllocateRoomId(null);
      setAllocateStudent("");
      await load();
    } catch (error) {
      setNotice({ kind: "error", text: error instanceof ApiFailure ? error.error.message : "Could not allocate this room." });
    } finally {
      setBusy(false);
    }
  }

  async function vacate(id: number) {
    setBusy(true);
    try {
      await api.vacateAllocation(id);
      await load();
    } catch (error) {
      setNotice({ kind: "error", text: error instanceof ApiFailure ? error.error.message : "Could not vacate this allocation." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Hostel</h1>
          <p className="page-subtitle">Room inventory and allocation</p>
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
          <span>Could not load the hostel records. Try again shortly.</span>
        </div>
      ) : null}

      {canManageRooms ? (
        <div className="card">
          <div className="card__header">
            <span className="card__icon">
              <BedIcon size={18} />
            </span>
            <h2>Add a room</h2>
          </div>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <div className="field" style={{ flex: 1, minWidth: 140 }}>
              <label htmlFor="new-building">Building</label>
              <input id="new-building" value={newBuilding} onChange={(event) => setNewBuilding(event.target.value)} />
            </div>
            <div className="field" style={{ width: 100 }}>
              <label htmlFor="new-room">Room no.</label>
              <input id="new-room" value={newRoomNumber} onChange={(event) => setNewRoomNumber(event.target.value)} />
            </div>
            <div className="field" style={{ width: 90 }}>
              <label htmlFor="new-capacity">Capacity</label>
              <input id="new-capacity" value={newCapacity} onChange={(event) => setNewCapacity(event.target.value)} />
            </div>
            <div className="field" style={{ width: 140 }}>
              <label htmlFor="new-gender">Restricted to</label>
              <select id="new-gender" value={newGender} onChange={(event) => setNewGender(event.target.value)}>
                <option value="female">Female</option>
                <option value="male">Male</option>
              </select>
            </div>
          </div>
          <button type="button" disabled={busy} onClick={() => void addRoom()}>
            Add room
          </button>
        </div>
      ) : null}

      {canViewRooms ? (
        <>
          <div className="grid">
            <div className="card stat stat--accent-blue">
              <div className="stat__top">
                <span className="stat__label">Rooms</span>
                <span className="stat__icon">
                  <BedIcon size={18} />
                </span>
              </div>
              <div className="stat__value">{rooms.length}</div>
            </div>
            <div className="card stat stat--accent-teal">
              <div className="stat__top">
                <span className="stat__label">Available beds</span>
                <span className="stat__icon">
                  <BedIcon size={18} />
                </span>
              </div>
              <div className="stat__value">{rooms.reduce((sum, room) => sum + room.available_beds, 0)}</div>
            </div>
          </div>

          <div className="section-title">Rooms</div>
          <div className="card">
            {state !== "loading" && rooms.length === 0 ? (
              <div className="empty-state">
                <span className="empty-state__title">No rooms yet</span>
              </div>
            ) : (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Room</th>
                      <th>Restricted to</th>
                      <th>Occupancy</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {rooms.map((room) => (
                      <tr key={room.id}>
                        <td className="cell-primary">
                          {room.building} {room.room_number}
                        </td>
                        <td style={{ textTransform: "capitalize" }}>{room.gender_restriction}</td>
                        <td>
                          <span className={`pill ${room.available_beds > 0 ? "pill--synced" : "pill--failed"}`}>
                            {room.occupied_beds} / {room.capacity}
                          </span>
                        </td>
                        <td>
                          {canAllocate && room.available_beds > 0 ? (
                            allocateRoomId === room.id ? (
                              <div style={{ display: "flex", gap: 6 }}>
                                <input
                                  value={allocateStudent}
                                  onChange={(event) => setAllocateStudent(event.target.value)}
                                  placeholder="Student ID"
                                  style={{ width: 90 }}
                                />
                                <select value={allocateYear} onChange={(event) => setAllocateYear(event.target.value)}>
                                  <option value="">Year</option>
                                  {academicYears.map((year) => (
                                    <option key={year.id} value={year.id}>
                                      {year.name}
                                    </option>
                                  ))}
                                </select>
                                <button type="button" className="sm" disabled={busy} onClick={() => void allocate()}>
                                  Allocate
                                </button>
                              </div>
                            ) : (
                              <button type="button" className="sm secondary" onClick={() => setAllocateRoomId(room.id)}>
                                Allocate
                              </button>
                            )
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      ) : null}

      <div className="section-title">Allocations</div>
      <div className="card">
        {state !== "loading" && allocations.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__title">No allocations</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Student</th>
                  <th>Room</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {allocations.map((allocation) => (
                  <tr key={allocation.id}>
                    <td style={{ fontFamily: "var(--mono)" }}>{allocation.student_number}</td>
                    <td>{allocation.room_label}</td>
                    <td>
                      <span className={`pill ${allocation.status === "active" ? "pill--synced" : ""}`}>{allocation.status}</span>
                    </td>
                    <td>
                      {canVacate && allocation.status === "active" ? (
                        <button type="button" className="sm ghost" disabled={busy} onClick={() => void vacate(allocation.id)}>
                          Vacate
                        </button>
                      ) : null}
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
