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
    await load();
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
        <button
          type="button"
          className="button-secondary"
          onClick={async () => {
            await api(`/admin/events/${event.id}/coupons/issue`, { method: "POST" }, csrf);
            alert("Missing coupons issued.");
          }}
        >
          Issue missing
        </button>
      </form>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((template) => (
          <article className="card p-5" key={template.id}>
            <Ticket className="text-leaf-600" />
            <strong className="mt-3 block">{template.name}</strong>
            <div className="mt-2"><StatusBadge status={template.active ? "active" : "disabled"} /></div>
            <p className="text-sm text-black/45">
              {template.vendor_id ? vendors.find((vendor) => vendor.id === template.vendor_id)?.name : "Any vendor"}
            </p>
          </article>
        ))}
      </div>
    </div>
  );
}
