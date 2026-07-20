"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Ticket } from "lucide-react";
import { api } from "@/lib/api";
import { Empty, Field } from "./AdminUi";
import { StatusBadge } from "./StatusBadge";
import type { CouponTemplate, Event, Vendor } from "./types";

export function CouponsPanel({ event, csrf }: { event: Event; csrf: string }) {
  const [items, setItems] = useState<CouponTemplate[]>([]);
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [selectedTemplateIds, setSelectedTemplateIds] = useState<Set<number>>(new Set());
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    const [templatesResult, vendorsResult] = await Promise.all([
      api<{ templates: CouponTemplate[] }>(`/admin/events/${event.id}/coupon-templates`),
      api<{ vendors: Vendor[] }>(`/admin/events/${event.id}/vendors`),
    ]);
    setItems(templatesResult.templates);
    setVendors(vendorsResult.vendors);
  }, [event.id]);

  useEffect(() => {
    void load();
  }, [load]);

  if (event.mode === "money") {
    return <Empty text="Coupons are not enabled for this event." />;
  }

  async function submit(submitEvent: FormEvent<HTMLFormElement>) {
    submitEvent.preventDefault();
    const formElement = submitEvent.currentTarget;
    const form = new FormData(formElement);
    setError("");
    try {
      await api(
        `/admin/events/${event.id}/coupon-templates`,
        {
          method: "POST",
          body: JSON.stringify({
            name: form.get("name"),
            vendor_id: form.get("vendor") ? Number(form.get("vendor")) : null,
            sort_order: items.length + 1,
          }),
        },
        csrf,
      );
      formElement.reset();
      setNotice("Coupon template created.");
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not create the coupon.");
    }
  }

  async function issueSelected() {
    if (!selectedTemplateIds.size) return;
    setError("");
    try {
      const result = await api<{ issued: number }>(
        `/admin/events/${event.id}/coupons/issue`,
        {
          method: "POST",
          body: JSON.stringify({ template_ids: Array.from(selectedTemplateIds) }),
        },
        csrf,
      );
      setNotice(`${result.issued} missing coupon${result.issued === 1 ? "" : "s"} issued.`);
      setSelectedTemplateIds(new Set());
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not issue coupons.");
    }
  }

  return (
    <div>
      <form onSubmit={submit} className="card flex flex-col gap-3 p-5 md:flex-row md:items-end">
        <Field label="Coupon name"><input className="input" name="name" required /></Field>
        <Field label="Vendor restriction">
          <select className="input" name="vendor">
            <option value="">Universal</option>
            {vendors.map((vendor) => <option value={vendor.id} key={vendor.id}>{vendor.name}</option>)}
          </select>
        </Field>
        <button className="button">Add template</button>
        <button type="button" className="button-secondary" onClick={() => void issueSelected()} disabled={!selectedTemplateIds.size}>
          Issue missing selected ({selectedTemplateIds.size})
        </button>
      </form>
      {notice && <div className="alert-success mt-4 text-sm">{notice}</div>}
      {error && <div className="alert-error mt-4 text-sm">{error}</div>}
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((template) => (
          <label className={`card flex cursor-pointer gap-3 p-5 ${selectedTemplateIds.has(template.id) ? "ring-2 ring-leaf-500" : ""}`} key={template.id}>
            <input
              type="checkbox"
              className="mt-1"
              disabled={!template.active}
              checked={selectedTemplateIds.has(template.id)}
              onChange={(changeEvent) => {
                const next = new Set(selectedTemplateIds);
                if (changeEvent.target.checked) next.add(template.id);
                else next.delete(template.id);
                setSelectedTemplateIds(next);
              }}
            />
            <span>
              <Ticket className="text-leaf-600" />
              <strong className="mt-3 block">{template.name}</strong>
              <span className="mt-2 block"><StatusBadge status={template.active ? "active" : "disabled"} /></span>
              <span className="text-sm text-black/45">
                {template.vendor_id ? vendors.find((vendor) => vendor.id === template.vendor_id)?.name : "Any vendor"}
              </span>
            </span>
          </label>
        ))}
      </div>
    </div>
  );
}
