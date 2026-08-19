"use client";

/** My fees & payments (FR-STU-08…10) — invoices, receipts and a running
 * balance for the signed-in student. */

import { useEffect, useState } from "react";

import { CreditCardIcon } from "@/components/icons";
import { ApiFailure, api } from "@/lib/api";

interface Invoice {
  id: number;
  invoice_number: string;
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
  receipt_number: string;
}

const STATUS_PILL: Record<string, string> = {
  paid: "pill--synced",
  confirmed: "pill--synced",
  issued: "pill--pending",
  pending: "pill--pending",
  partially_paid: "pill--pending",
};

export default function MyFinancePage() {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "offline" | "error">("loading");

  useEffect(() => {
    Promise.all([api.invoices(), api.payments()])
      .then(([invoicePage, paymentPage]) => {
        setInvoices(invoicePage.results);
        setPayments(paymentPage.results);
        setState("ready");
      })
      .catch((error) => setState(error instanceof ApiFailure && error.offline ? "offline" : "error"));
  }, []);

  const balance = invoices.reduce((sum, invoice) => sum + Number(invoice.balance), 0);
  const currency = invoices[0]?.currency ?? "SSP";

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Fees &amp; payments</h1>
          <p className="page-subtitle">Your invoices, receipts and balance</p>
        </div>
      </div>

      {state === "offline" ? (
        <div className="alert alert--warning">
          <span>No connection. Showing whatever loaded earlier on this device.</span>
        </div>
      ) : null}
      {state === "error" ? (
        <div className="alert alert--error">
          <span>Could not load your fee records. Try again shortly.</span>
        </div>
      ) : null}

      <div className="grid">
        <div className={`card stat stat--accent-${balance > 0 ? "rose" : "teal"}`}>
          <div className="stat__top">
            <span className="stat__label">Outstanding balance</span>
            <span className="stat__icon">
              <CreditCardIcon size={18} />
            </span>
          </div>
          <div className="stat__value">
            {balance > 0 ? balance.toLocaleString() : "0"} {currency}
          </div>
          <div className="stat__foot">{balance > 0 ? "Payable at the finance office" : "Nothing owed"}</div>
        </div>
      </div>

      <div className="section-title">Invoices</div>
      <div className="card">
        {state !== "loading" && invoices.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__title">No invoices yet</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Invoice</th>
                  <th>Amount</th>
                  <th>Balance</th>
                  <th>Due</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {invoices.map((invoice) => (
                  <tr key={invoice.id}>
                    <td style={{ fontFamily: "var(--mono)" }}>{invoice.invoice_number}</td>
                    <td>
                      {invoice.net_amount} {invoice.currency}
                    </td>
                    <td>
                      {invoice.balance} {invoice.currency}
                    </td>
                    <td>{invoice.due_date}</td>
                    <td>
                      <span className={`pill ${STATUS_PILL[invoice.status] ?? ""}`}>{invoice.status.replace(/_/g, " ")}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="section-title">Receipts</div>
      <div className="card">
        {state !== "loading" && payments.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__title">No payments recorded yet</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Receipt</th>
                  <th>Method</th>
                  <th>Amount</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {payments.map((payment) => (
                  <tr key={payment.id}>
                    <td style={{ fontFamily: "var(--mono)" }}>{payment.receipt_number || "—"}</td>
                    <td>{payment.method.replace(/_/g, " ")}</td>
                    <td>
                      {payment.amount} {payment.currency}
                    </td>
                    <td>
                      <span className={`pill ${STATUS_PILL[payment.status] ?? ""}`}>{payment.status}</span>
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
