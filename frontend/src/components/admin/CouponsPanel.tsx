"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Edit3, Power, Ticket, Trash2 } from "lucide-react";
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
  const [editing, setEditing] = useState<CouponTemplate | null>(null);
  const [instances, setInstances] = useState<Array<{ id: number; code: string; name: string; participant_name: string; participant_code: string; status: string }>>([]);
  const load = useCallback(async () => {
    const [templatesResult, vendorsResult, instancesResult] = await Promise.all([
      api<{ templates: CouponTemplate[] }>(`/admin/events/${event.id}/coupon-templates`),
      api<{ vendors: Vendor[] }>(`/admin/events/${event.id}/vendors`),
      api<{ coupons: typeof instances }>(`/admin/events/${event.id}/coupon-instances`),
    ]);
    setItems(templatesResult.templates);
    setVendors(vendorsResult.vendors);
    setInstances(instancesResult.coupons);
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
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not issue coupons.");
    }
  }

  async function setAll(enabled: boolean, templateId?: number) {
    setError("");
    try {
      const result = await api<{ updated: number }>(
        `/admin/events/${event.id}/coupons/status`,
        { method: "PATCH", body: JSON.stringify({ enabled, template_id: templateId ?? null }) },
        csrf,
      );
      setNotice(`${result.updated} issued coupon${result.updated === 1 ? "" : "s"} ${enabled ? "enabled" : "disabled"}.`);
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not update coupons.");
    }
  }

  async function saveTemplate(submitEvent: FormEvent<HTMLFormElement>) {
    submitEvent.preventDefault();
    if (!editing) return;
    const form = new FormData(submitEvent.currentTarget);
    try {
      await api(`/admin/events/${event.id}/coupon-templates/${editing.id}`, {
        method: "PUT",
        body: JSON.stringify({
          name: form.get("name"),
          vendor_id: form.get("vendor") ? Number(form.get("vendor")) : null,
          sort_order: editing.sort_order,
          active: form.get("active") === "on",
          apply_to_instances: true,
        }),
      }, csrf);
      setEditing(null);
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not update coupon.");
    }
  }

  async function removeTemplate(template: CouponTemplate) {
    if (!window.confirm(`Delete ${template.name}? Issued coupons must be disabled instead.`)) return;
    try {
      await api(`/admin/events/${event.id}/coupon-templates/${template.id}`, { method: "DELETE" }, csrf);
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not delete coupon.");
    }
  }

  async function setInstance(id: number, enabled: boolean) {
    try {
      await api(`/admin/events/${event.id}/coupons/${id}/status`, {
        method: "PATCH", body: JSON.stringify({ enabled }),
      }, csrf);
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not update coupon.");
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
        <button type="button" className="button-secondary" onClick={() => void setAll(false)}>Disable all</button>
        <button type="button" className="button-secondary" onClick={() => void setAll(true)}>Enable all</button>
      </form>
      {notice && <div className="alert-success mt-4 text-sm">{notice}</div>}
      {error && <div className="alert-error mt-4 text-sm">{error}</div>}
      {editing && (
        <form onSubmit={saveTemplate} className="card mt-4 grid gap-3 p-5 md:grid-cols-3">
          <Field label="Coupon name"><input className="input" name="name" defaultValue={editing.name} required /></Field>
          <Field label="Vendor restriction"><select className="input" name="vendor" defaultValue={editing.vendor_id ?? ""}><option value="">Universal</option>{vendors.map((vendor) => <option value={vendor.id} key={vendor.id}>{vendor.name}</option>)}</select></Field>
          <label className="flex items-center gap-2 self-end pb-3 text-sm"><input type="checkbox" name="active" defaultChecked={editing.active} /> Active (also update issued coupons)</label>
          <div className="flex gap-2 md:col-span-3"><button className="button">Save</button><button type="button" className="button-secondary" onClick={() => setEditing(null)}>Cancel</button></div>
        </form>
      )}
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((template) => (
          <article className={`card flex gap-3 p-5 ${selectedTemplateIds.has(template.id) ? "ring-2 ring-leaf-500" : ""}`} key={template.id}>
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
            <div className="min-w-0 flex-1">
              <Ticket className="text-leaf-600" />
              <strong className="mt-3 block">{template.name}</strong>
              <span className="mt-2 block"><StatusBadge status={template.active ? "active" : "disabled"} /></span>
              <span className="text-sm text-black/45">
                {template.vendor_id ? vendors.find((vendor) => vendor.id === template.vendor_id)?.name : "Any vendor"}
              </span>
              <div className="mt-4 flex gap-2">
                <button className="button-secondary min-h-9 px-2" title="Edit coupon" onClick={() => setEditing(template)}><Edit3 size={15} /></button>
                <button className="button-secondary min-h-9 px-2" title={template.active ? "Disable coupon" : "Enable coupon"} onClick={() => void setAll(!template.active, template.id)}><Power size={15} /></button>
                <button className="button-secondary min-h-9 px-2 text-red-700" title="Delete coupon" onClick={() => void removeTemplate(template)}><Trash2 size={15} /></button>
              </div>
            </div>
          </article>
        ))}
      </div>
      {!!instances.length && (
        <div className="card mt-6 overflow-x-auto">
          <div className="border-b border-black/10 p-5"><h3 className="text-lg font-semibold">Issued coupons</h3><p className="text-sm text-black/45">Enable or disable a coupon for one participant.</p></div>
          <table className="data-table"><thead><tr><th>Participant</th><th>Coupon</th><th>Code</th><th>Status</th><th>Action</th></tr></thead>
            <tbody>{instances.map((coupon) => <tr key={coupon.id}>
              <td><strong>{coupon.participant_name}</strong><div className="text-xs text-black/45">{coupon.participant_code}</div></td>
              <td>{coupon.name}</td><td className="font-mono text-xs">{coupon.code}</td><td><StatusBadge status={coupon.status} /></td>
              <td>{(coupon.status === "available" || coupon.status === "disabled") && <button className="button-secondary min-h-9" onClick={() => void setInstance(coupon.id, coupon.status === "disabled")}><Power size={14} /> {coupon.status === "available" ? "Disable" : "Enable"}</button>}</td>
            </tr>)}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}
