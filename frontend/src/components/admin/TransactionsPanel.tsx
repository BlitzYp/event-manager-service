"use client";

import { useCallback, useEffect, useState } from "react";
import { Download, Filter, RotateCcw } from "lucide-react";
import { api, money } from "@/lib/api";
import { Empty } from "./AdminUi";
import { StatusBadge } from "./StatusBadge";
import type { Event, Transaction, Vendor } from "./types";

type TransactionFilters = {
  search: string;
  date_from: string;
  date_to: string;
  status: string;
  type: string;
  vendor_id: string;
};

const emptyFilters: TransactionFilters = {
  search: "",
  date_from: "",
  date_to: "",
  status: "",
  type: "",
  vendor_id: "",
};

export function TransactionsPanel({ event }: { event: Event }) {
  const [items, setItems] = useState<Transaction[]>([]);
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [draftFilters, setDraftFilters] = useState(emptyFilters);
  const [appliedFilters, setAppliedFilters] = useState(emptyFilters);
  const [error, setError] = useState("");

  const queryString = useCallback((filters: TransactionFilters) => {
    const query = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value) query.set(key, value);
    });
    return query.toString();
  }, []);

  const load = useCallback(async () => {
    setError("");
    try {
      const query = queryString(appliedFilters);
      const [transactions, vendorResult] = await Promise.all([
        api<{ transactions: Transaction[] }>(
          `/admin/events/${event.id}/transactions${query ? `?${query}` : ""}`,
        ),
        api<{ vendors: Vendor[] }>(`/admin/events/${event.id}/vendors`),
      ]);
      setItems(transactions.transactions);
      setVendors(vendorResult.vendors);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not load transactions.");
    }
  }, [appliedFilters, event.id, queryString]);

  useEffect(() => {
    void load();
  }, [load]);

  const exportQuery = queryString(appliedFilters);
  const exportSuffix = exportQuery ? `?${exportQuery}` : "";

  return (
    <div>
      <form
        className="card mb-4 grid gap-3 p-4 md:grid-cols-2 xl:grid-cols-6"
        onSubmit={(submitEvent) => {
          submitEvent.preventDefault();
          setAppliedFilters(draftFilters);
        }}
      >
        <input
          className="input md:col-span-2 xl:col-span-6"
          placeholder="Participant, code, group, vendor, or reference"
          value={draftFilters.search}
          onChange={(changeEvent) => setDraftFilters({ ...draftFilters, search: changeEvent.target.value })}
        />
        <input
          className="input"
          type="date"
          aria-label="From date"
          value={draftFilters.date_from}
          onChange={(changeEvent) => setDraftFilters({ ...draftFilters, date_from: changeEvent.target.value })}
        />
        <input
          className="input"
          type="date"
          aria-label="Until date"
          min={draftFilters.date_from || undefined}
          value={draftFilters.date_to}
          onChange={(changeEvent) => setDraftFilters({ ...draftFilters, date_to: changeEvent.target.value })}
        />
        <select className="input" aria-label="Transaction status" value={draftFilters.status} onChange={(changeEvent) => setDraftFilters({ ...draftFilters, status: changeEvent.target.value })}>
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
          <option value="cancelled">Cancelled</option>
          <option value="reversed">Reversed</option>
        </select>
        <select className="input" aria-label="Transaction type" value={draftFilters.type} onChange={(changeEvent) => setDraftFilters({ ...draftFilters, type: changeEvent.target.value })}>
          <option value="">All types</option>
          <option value="initial_credit">Initial credit</option>
          <option value="admin_credit">Admin credit</option>
          <option value="admin_debit">Admin debit</option>
          <option value="vendor_debit">Vendor payment</option>
          <option value="reversal">Reversal</option>
        </select>
        <select className="input" aria-label="Vendor" value={draftFilters.vendor_id} onChange={(changeEvent) => setDraftFilters({ ...draftFilters, vendor_id: changeEvent.target.value })}>
          <option value="">All vendors</option>
          {vendors.map((vendor) => <option key={vendor.id} value={vendor.id}>{vendor.name}</option>)}
        </select>
        <div className="flex gap-2">
          <button className="button px-3" title="Apply filters"><Filter size={17} /></button>
          <button
            className="button-secondary px-3"
            type="button"
            title="Clear filters"
            onClick={() => {
              setDraftFilters(emptyFilters);
              setAppliedFilters(emptyFilters);
            }}
          >
            <RotateCcw size={17} />
          </button>
        </div>
        <div className="flex flex-wrap gap-2 md:col-span-2 xl:col-span-6 xl:justify-end">
          <a className="button-secondary" href={`/api/v1/admin/events/${event.id}/transactions/export.csv${exportSuffix}`}>
            <Download size={16} /> CSV
          </a>
          <a className="button-secondary" href={`/api/v1/admin/events/${event.id}/transactions/export.xlsx${exportSuffix}`}>
            <Download size={16} /> Excel
          </a>
        </div>
      </form>

      {error && <div className="alert-error mb-4 text-sm">{error}</div>}
      <div className="card overflow-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th>Date / reference</th>
              <th>Participant</th>
              <th>Vendor</th>
              <th>Type</th>
              <th>Status</th>
              <th>Amount</th>
            </tr>
          </thead>
          <tbody>
            {items.map((transaction) => {
              const debit = transaction.type === "vendor_debit" || transaction.type === "admin_debit";
              return (
                <tr key={transaction.id}>
                  <td>
                    {new Date(transaction.created_at).toLocaleString()}
                    <div className="font-mono text-xs text-black/40">{transaction.reference}</div>
                  </td>
                  <td>
                    <strong>{transaction.participant_name}</strong>
                    <div className="text-xs text-black/40">{transaction.participant_code} · {transaction.group || "—"}</div>
                  </td>
                  <td>{transaction.vendor_name || "Administrator"}</td>
                  <td className="capitalize">{transaction.type.replaceAll("_", " ")}</td>
                  <td><StatusBadge status={transaction.status} /></td>
                  <td className={debit ? "font-semibold text-red-700" : "font-semibold text-emerald-700"}>
                    {debit ? "−" : "+"}{money(transaction.amount_minor, event.currency)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {!items.length && <Empty text="No transactions match these filters." />}
      </div>
    </div>
  );
}
