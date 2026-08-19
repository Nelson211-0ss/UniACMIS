"use client";

/** Finance (FR-FIN-01…08). A student sees their own invoices, payments and
 * balance — the API scopes the list automatically. Generating invoices,
 * recording payments and the defaulter report are finance-only actions. */

import { useEffect, useState } from "react";

import { CreditCardIcon } from "@/components/icons";
import { ApiFailure, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Invoice {
  id: number;
  invoice_number: string;
  student: number;
  semester: number;
  amount: string;
  net_amount: string;
  balance: string;
  currency: string;
  status: string;
  due_date: string;
}

interface Payment {
  id: number;
  invoice: number;
  method: string;
  amount: string;
  currency: string;
  status: string;
  reference: string;
  receipt_number: string;
}

interface Defaulter {
  invoice_number: string;
  student_number: string;
  student_name: string;
  balance: string;
  currency: string;
  days_overdue: number;
}

const STATUS_PILL: Record<string, string> = {
  paid: "pill--synced",
  confirmed: "pill--synced",
  issued: "pill--pending",
  pending: "pill--pending",
  partially_paid: "pill--pending",
  cancelled: "pill--failed",
  failed: "pill--failed",
  written_off: "pill--failed",
};

export default function FinancePage() {
  const { can, hasRole } = useAuth();
  const canManage = can("finance.add_invoice");
  const canViewDefaulters = can("finance.view_defaulterreport");

  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [defaulters, setDefaulters] = useState<Defaulter[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "offline" | "error">("loading");
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  const [genStudent, setGenStudent] = useState("");
  const [genSemester, setGenSemester] = useState("");
  const [semesters, setSemesters] = useState<Array<{ id: number; name: string }>>([]);
  const [payInvoice, setPayInvoice] = useState("");
  const [payMethod, setPayMethod] = useState("cash");
  const [payAmount, setPayAmount] = useState("");
  const [payReference, setPayReference] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const [invoicePage, paymentPage] = await Promise.all([
        api.invoices(),
        api.payments(),
      ]);
      setInvoices(invoicePage.results);
      setPayments(paymentPage.results);
      if (canViewDefaulters) {
        setDefaulters(await api.defaulterReport().catch(() => []));
      }
      if (canManage) {
        const semesterPage = await api.semesters().catch(() => ({ results: [] }));
        setSemesters(semesterPage.results);
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

  const balance = invoices.reduce((sum, invoice) => sum + Number(invoice.balance), 0);

  async function generateInvoice() {
    if (!genStudent || !genSemester) return;
    setBusy(true);
    setNotice(null);
    try {
      await api.generateInvoice(Number(genStudent), Number(genSemester));
      setNotice({ kind: "success", text: "Invoice generated." });
      setGenStudent("");
      await load();
    } catch (error) {
      setNotice({
        kind: "error",
        text: error instanceof ApiFailure ? error.error.message : "Could not generate the invoice.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function recordPayment() {
    if (!payInvoice || !payAmount || !payReference) return;
    setBusy(true);
    setNotice(null);
    try {
      await api.recordPayment({
        invoice: Number(payInvoice),
        method: payMethod,
        amount: payAmount,
        reference: payReference,
      });
      setNotice({ kind: "success", text: "Payment recorded." });
      setPayInvoice("");
      setPayAmount("");
      setPayReference("");
      await load();
    } catch (error) {
      setNotice({
        kind: "error",
        text: error instanceof ApiFailure ? error.error.message : "Could not record the payment.",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Finance</h1>
          <p className="page-subtitle">
            {hasRole("finance") ? "Fee structures, invoices and payments" : "Your invoices and payments"}
          </p>
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
          <span>Could not load finance records. Try again shortly.</span>
        </div>
      ) : null}

      <div className="grid">
        <div className="card stat stat--accent-blue">
          <div className="stat__top">
            <span className="stat__label">Outstanding balance</span>
            <span className="stat__icon">
              <CreditCardIcon size={18} />
            </span>
          </div>
          <div className="stat__value">{balance > 0 ? balance.toLocaleString() : "0"}</div>
          <div className="stat__foot">{invoices[0]?.currency ?? "SSP"}</div>
        </div>
        <div className="card stat stat--accent-teal">
          <div className="stat__top">
            <span className="stat__label">Invoices</span>
            <span className="stat__icon">
              <CreditCardIcon size={18} />
            </span>
          </div>
          <div className="stat__value">{invoices.length}</div>
        </div>
        <div className="card stat stat--accent-amber">
          <div className="stat__top">
            <span className="stat__label">Payments</span>
            <span className="stat__icon">
              <CreditCardIcon size={18} />
            </span>
          </div>
          <div className="stat__value">{payments.length}</div>
        </div>
      </div>

      {canManage ? (
        <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))" }}>
          <div className="card">
            <div className="card__header">
              <h2>Generate an invoice</h2>
            </div>
            <div className="field">
              <label htmlFor="gen-student">Student ID (numeric)</label>
              <input
                id="gen-student"
                value={genStudent}
                onChange={(event) => setGenStudent(event.target.value)}
                placeholder="e.g. 42"
              />
            </div>
            <div className="field">
              <label htmlFor="gen-semester">Semester</label>
              <select
                id="gen-semester"
                value={genSemester}
                onChange={(event) => setGenSemester(event.target.value)}
              >
                <option value="">Select a semester</option>
                {semesters.map((semester) => (
                  <option key={semester.id} value={semester.id}>
                    {semester.name}
                  </option>
                ))}
              </select>
            </div>
            <button type="button" disabled={busy} onClick={() => void generateInvoice()}>
              Generate
            </button>
          </div>

          <div className="card">
            <div className="card__header">
              <h2>Record a payment</h2>
            </div>
            <div className="field">
              <label htmlFor="pay-invoice">Invoice ID</label>
              <input
                id="pay-invoice"
                value={payInvoice}
                onChange={(event) => setPayInvoice(event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="pay-method">Method</label>
              <select id="pay-method" value={payMethod} onChange={(event) => setPayMethod(event.target.value)}>
                <option value="cash">Cash</option>
                <option value="cheque">Cheque</option>
                <option value="bank_slip">Bank slip</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="pay-amount">Amount</label>
              <input id="pay-amount" value={payAmount} onChange={(event) => setPayAmount(event.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="pay-reference">Reference</label>
              <input
                id="pay-reference"
                value={payReference}
                onChange={(event) => setPayReference(event.target.value)}
              />
            </div>
            <button type="button" disabled={busy} onClick={() => void recordPayment()}>
              Record payment
            </button>
          </div>
        </div>
      ) : null}

      <div className="section-title">Invoices</div>
      <div className="card">
        {state !== "loading" && invoices.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__title">No invoices</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Invoice</th>
                  <th>Amount</th>
                  <th>Due</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {invoices.map((invoice) => (
                  <tr key={invoice.id}>
                    <td className="cell-primary" style={{ fontFamily: "var(--mono)" }}>
                      {invoice.invoice_number}
                    </td>
                    <td>
                      {invoice.net_amount} {invoice.currency}
                    </td>
                    <td>{invoice.due_date}</td>
                    <td>
                      <span className={`pill ${STATUS_PILL[invoice.status] ?? ""}`}>
                        {invoice.status.replace(/_/g, " ")}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="section-title">Payments</div>
      <div className="card">
        {state !== "loading" && payments.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__title">No payments</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Reference</th>
                  <th>Method</th>
                  <th>Amount</th>
                  <th>Status</th>
                  <th>Receipt</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {payments.map((payment) => (
                  <tr key={payment.id}>
                    <td style={{ fontFamily: "var(--mono)" }}>{payment.reference}</td>
                    <td>{payment.method.replace(/_/g, " ")}</td>
                    <td>
                      {payment.amount} {payment.currency}
                    </td>
                    <td>
                      <span className={`pill ${STATUS_PILL[payment.status] ?? ""}`}>{payment.status}</span>
                    </td>
                    <td style={{ fontFamily: "var(--mono)" }}>{payment.receipt_number || "—"}</td>
                    <td>
                      {canManage && payment.status === "pending" ? (
                        <button
                          type="button"
                          className="sm secondary"
                          onClick={() => void api.confirmPayment(payment.id).then(load)}
                        >
                          Confirm
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

      {canViewDefaulters ? (
        <>
          <div className="section-title">Defaulter report</div>
          <div className="card">
            {defaulters.length === 0 ? (
              <div className="empty-state">
                <span className="empty-state__title">No outstanding balances</span>
              </div>
            ) : (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Student</th>
                      <th>Invoice</th>
                      <th>Balance</th>
                      <th>Days overdue</th>
                    </tr>
                  </thead>
                  <tbody>
                    {defaulters.map((row) => (
                      <tr key={row.invoice_number}>
                        <td className="cell-primary">
                          {row.student_name}
                          <div className="text-sm muted">{row.student_number}</div>
                        </td>
                        <td style={{ fontFamily: "var(--mono)" }}>{row.invoice_number}</td>
                        <td>
                          {row.balance} {row.currency}
                        </td>
                        <td>
                          <span className={row.days_overdue > 0 ? "pill pill--failed" : "pill"}>
                            {row.days_overdue}
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
      ) : null}
    </>
  );
}
