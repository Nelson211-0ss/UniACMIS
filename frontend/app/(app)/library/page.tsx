"use client";

/** Library (FR-LIB-01…03). The catalogue is open to every signed-in user;
 * checkout, return and fine-waiver are librarian actions. */

import { useEffect, useState } from "react";

import { DonutChartCard } from "@/components/charts/DonutChartCard";
import { BookOpenIcon } from "@/components/icons";
import { ApiFailure, api } from "@/lib/api";
import { CHART_STATUS } from "@/lib/chartColors";
import { useAuth } from "@/lib/auth";

interface LibraryItem {
  id: number;
  title: string;
  author: string;
  item_type: string;
  available_copies: number;
  total_copies: number;
  is_active: boolean;
}

interface Loan {
  id: number;
  item: number;
  item_title: string;
  borrower_number: string;
  due_date: string;
  returned_at: string | null;
  status: string;
  fine_amount: string;
  owed: string;
  currency: string;
  fine_waived: boolean;
}

const STATUS_PILL: Record<string, string> = {
  active: "pill--pending",
  returned: "pill--synced",
  lost: "pill--failed",
};

export default function LibraryPage() {
  const { can } = useAuth();
  const canCatalogue = can("library.add_libraryitem");
  const canCheckout = can("library.add_loan");
  const canReturn = can("library.change_loan");
  const canWaive = can("library.waive_fine");

  const [items, setItems] = useState<LibraryItem[]>([]);
  const [loans, setLoans] = useState<Loan[]>([]);
  const [search, setSearch] = useState("");
  const [state, setState] = useState<"loading" | "ready" | "offline" | "error">("loading");
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const [newTitle, setNewTitle] = useState("");
  const [newAuthor, setNewAuthor] = useState("");
  const [newCopies, setNewCopies] = useState("1");
  const [checkoutFor, setCheckoutFor] = useState<number | null>(null);
  const [borrowerId, setBorrowerId] = useState("");
  const [borrowerType, setBorrowerType] = useState<"student" | "staff">("student");
  const [waiveFor, setWaiveFor] = useState<number | null>(null);
  const [waiveReason, setWaiveReason] = useState("");

  async function load() {
    try {
      const query = search.trim() ? `?search=${encodeURIComponent(search.trim())}&page_size=50` : "?page_size=50";
      const [itemPage, loanPage] = await Promise.all([
        api.libraryItems(query),
        api.loans().catch(() => ({ results: [] as Loan[] })),
      ]);
      setItems(itemPage.results);
      setLoans(loanPage.results);
      setState("ready");
    } catch (error) {
      setState(error instanceof ApiFailure && error.offline ? "offline" : "error");
    }
  }

  useEffect(() => {
    const timer = setTimeout(() => void load(), 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const loanStatusSlices = Object.entries(
    loans.reduce<Record<string, number>>((acc, loan) => {
      acc[loan.status] = (acc[loan.status] ?? 0) + 1;
      return acc;
    }, {}),
  ).map(([status, count]) => ({
    key: status,
    label: status,
    value: count,
    color: status === "active" ? CHART_STATUS.warning : status === "lost" ? CHART_STATUS.bad : CHART_STATUS.good,
  }));

  const activeLoans = loans.filter((loan) => loan.status === "active").length;
  const finesOwed = loans.reduce((sum, loan) => sum + Number(loan.owed), 0);

  async function addItem() {
    if (!newTitle.trim()) return;
    setBusy(true);
    setNotice(null);
    try {
      await api.createLibraryItem({ title: newTitle, author: newAuthor, item_type: "book", total_copies: Number(newCopies) || 1 });
      setNotice({ kind: "success", text: "Item added to the catalogue." });
      setNewTitle("");
      setNewAuthor("");
      await load();
    } catch (error) {
      setNotice({ kind: "error", text: error instanceof ApiFailure ? error.error.message : "Could not add the item." });
    } finally {
      setBusy(false);
    }
  }

  async function checkout(itemId: number) {
    if (!borrowerId) return;
    setBusy(true);
    setNotice(null);
    try {
      await api.checkoutItem({
        item: itemId,
        ...(borrowerType === "student" ? { borrower_student: Number(borrowerId) } : { borrower_staff: Number(borrowerId) }),
      });
      setNotice({ kind: "success", text: "Checked out." });
      setCheckoutFor(null);
      setBorrowerId("");
      await load();
    } catch (error) {
      setNotice({ kind: "error", text: error instanceof ApiFailure ? error.error.message : "Could not check out this item." });
    } finally {
      setBusy(false);
    }
  }

  async function returnLoan(loanId: number) {
    setBusy(true);
    try {
      await api.returnLoan(loanId);
      await load();
    } catch (error) {
      setNotice({ kind: "error", text: error instanceof ApiFailure ? error.error.message : "Could not record the return." });
    } finally {
      setBusy(false);
    }
  }

  async function waive(loanId: number) {
    if (!waiveReason.trim()) return;
    setBusy(true);
    try {
      await api.waiveFine(loanId, waiveReason);
      setWaiveFor(null);
      setWaiveReason("");
      await load();
    } catch (error) {
      setNotice({ kind: "error", text: error instanceof ApiFailure ? error.error.message : "Could not waive the fine." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Library</h1>
          <p className="page-subtitle">Catalogue and circulation</p>
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

      {loans.length > 0 ? (
        <div className="grid--split">
          <div className="grid">
            <div className="card stat stat--accent-teal">
              <div className="stat__top">
                <span className="stat__label">Catalogue items</span>
                <span className="stat__icon">
                  <BookOpenIcon size={18} />
                </span>
              </div>
              <div className="stat__value">{items.length}</div>
            </div>
            <div className="card stat stat--accent-amber">
              <div className="stat__top">
                <span className="stat__label">Active loans</span>
                <span className="stat__icon">
                  <BookOpenIcon size={18} />
                </span>
              </div>
              <div className="stat__value">{activeLoans}</div>
            </div>
            <div className="card stat stat--accent-rose">
              <div className="stat__top">
                <span className="stat__label">Fines outstanding</span>
                <span className="stat__icon">
                  <BookOpenIcon size={18} />
                </span>
              </div>
              <div className="stat__value">{finesOwed > 0 ? finesOwed.toLocaleString() : "0"}</div>
            </div>
          </div>
          <DonutChartCard title="Loan status" data={loanStatusSlices} innerRadius={0} height={220} />
        </div>
      ) : null}

      {canCatalogue ? (
        <div className="card">
          <div className="card__header">
            <span className="card__icon">
              <BookOpenIcon size={18} />
            </span>
            <h2>Add an item</h2>
          </div>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <div className="field" style={{ flex: 2, minWidth: 180 }}>
              <label htmlFor="new-title">Title</label>
              <input id="new-title" value={newTitle} onChange={(event) => setNewTitle(event.target.value)} />
            </div>
            <div className="field" style={{ flex: 1, minWidth: 140 }}>
              <label htmlFor="new-author">Author</label>
              <input id="new-author" value={newAuthor} onChange={(event) => setNewAuthor(event.target.value)} />
            </div>
            <div className="field" style={{ width: 90 }}>
              <label htmlFor="new-copies">Copies</label>
              <input id="new-copies" value={newCopies} onChange={(event) => setNewCopies(event.target.value)} />
            </div>
          </div>
          <button type="button" disabled={busy} onClick={() => void addItem()}>
            Add to catalogue
          </button>
        </div>
      ) : null}

      <div className="card">
        <div className="field field--icon" style={{ marginBottom: 0 }}>
          <label htmlFor="search">Search the catalogue</label>
          <input id="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Title, author or ISBN" />
        </div>
      </div>

      <div className="card">
        {state !== "loading" && items.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__icon">
              <BookOpenIcon size={26} />
            </span>
            <span className="empty-state__title">No items match</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Type</th>
                  <th>Available</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td className="cell-primary">
                      {item.title}
                      <div className="text-sm muted">{item.author}</div>
                    </td>
                    <td>{item.item_type}</td>
                    <td>
                      <span className={`pill ${item.available_copies > 0 ? "pill--synced" : "pill--failed"}`}>
                        {item.available_copies} / {item.total_copies}
                      </span>
                    </td>
                    <td>
                      {canCheckout && item.available_copies > 0 ? (
                        checkoutFor === item.id ? (
                          <div style={{ display: "flex", gap: 6 }}>
                            <select value={borrowerType} onChange={(event) => setBorrowerType(event.target.value as "student" | "staff")}>
                              <option value="student">Student</option>
                              <option value="staff">Staff</option>
                            </select>
                            <input
                              value={borrowerId}
                              onChange={(event) => setBorrowerId(event.target.value)}
                              placeholder="ID"
                              style={{ width: 80 }}
                            />
                            <button type="button" className="sm" disabled={busy} onClick={() => void checkout(item.id)}>
                              Check out
                            </button>
                          </div>
                        ) : (
                          <button type="button" className="sm secondary" onClick={() => setCheckoutFor(item.id)}>
                            Check out
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

      <div className="section-title">Loans</div>
      <div className="card">
        {state !== "loading" && loans.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__title">No loans</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Item</th>
                  <th>Borrower</th>
                  <th>Due</th>
                  <th>Status</th>
                  <th>Owed</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {loans.map((loan) => (
                  <tr key={loan.id}>
                    <td>{loan.item_title}</td>
                    <td style={{ fontFamily: "var(--mono)" }}>{loan.borrower_number}</td>
                    <td>{loan.due_date}</td>
                    <td>
                      <span className={`pill ${STATUS_PILL[loan.status] ?? ""}`}>{loan.status}</span>
                    </td>
                    <td>
                      {Number(loan.owed) > 0 ? (
                        <span className="pill pill--failed">
                          {loan.owed} {loan.currency}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: 6 }}>
                        {canReturn && loan.status === "active" ? (
                          <button type="button" className="sm secondary" disabled={busy} onClick={() => void returnLoan(loan.id)}>
                            Return
                          </button>
                        ) : null}
                        {canWaive && Number(loan.owed) > 0 && !loan.fine_waived ? (
                          waiveFor === loan.id ? (
                            <>
                              <input
                                value={waiveReason}
                                onChange={(event) => setWaiveReason(event.target.value)}
                                placeholder="Reason"
                                style={{ width: 120 }}
                              />
                              <button type="button" className="sm" disabled={busy} onClick={() => void waive(loan.id)}>
                                Waive
                              </button>
                            </>
                          ) : (
                            <button type="button" className="sm ghost" onClick={() => setWaiveFor(loan.id)}>
                              Waive fine
                            </button>
                          )
                        ) : null}
                      </div>
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
