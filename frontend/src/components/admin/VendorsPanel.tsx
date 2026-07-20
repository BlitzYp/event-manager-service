"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Edit3, Power, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { Empty, Field } from "./AdminUi";
import { StatusBadge } from "./StatusBadge";
import type { Event, Vendor } from "./types";

export function VendorsPanel({ event, csrf }: { event: Event; csrf: string }) {
  const [items, setItems] = useState<Vendor[]>([]);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<Vendor | null>(null);
  const load = useCallback(async () => {
    const result = await api<{ vendors: Vendor[] }>(`/admin/events/${event.id}/vendors`);
    setItems(result.vendors);
  }, [event.id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function submit(submitEvent: FormEvent<HTMLFormElement>) {
    submitEvent.preventDefault();
    const formElement = submitEvent.currentTarget;
    const form = new FormData(formElement);
    try {
      await api(
        `/admin/events/${event.id}/vendors`,
        { method: "POST", body: JSON.stringify({ name: form.get("name"), pin: form.get("pin") }) },
        csrf,
      );
      formElement.reset();
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Create failed.");
    }
  }

  async function saveVendor(submitEvent: FormEvent<HTMLFormElement>) {
    submitEvent.preventDefault();
    if (!editing) return;
    const form = new FormData(submitEvent.currentTarget);
    setError("");
    try {
      await api(`/admin/events/${event.id}/vendors/${editing.id}`, {
        method: "PUT",
        body: JSON.stringify({
          name: form.get("name"),
          active: form.get("active") === "on",
          pin: form.get("pin") || null,
        }),
      }, csrf);
      setEditing(null);
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Update failed.");
    }
  }

  async function removeVendor(vendor: Vendor) {
    if (!window.confirm(`Delete ${vendor.name}? Existing audit entries will be preserved.`)) return;
    try {
      await api(`/admin/events/${event.id}/vendors/${vendor.id}`, { method: "DELETE" }, csrf);
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Delete failed.");
    }
  }

  async function toggleVendor(vendor: Vendor) {
    try {
      await api(`/admin/events/${event.id}/vendors/${vendor.id}`, {
        method: "PUT",
        body: JSON.stringify({ name: vendor.name, active: !vendor.active, pin: null }),
      }, csrf);
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Update failed.");
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
      <form onSubmit={submit} className="card p-5">
        <h3 className="text-xl font-semibold">Add vendor</h3>
        <Field label="Vendor name"><input className="input" name="name" required /></Field>
        <Field label="Six-digit PIN">
          <input className="input" name="pin" inputMode="numeric" pattern="\d{6}" maxLength={6} required />
        </Field>
        <button className="button mt-4 w-full">Create vendor</button>
        {error && <p className="mt-3 text-sm text-red-700">{error}</p>}
      </form>
      <div>
        {editing && (
          <form onSubmit={saveVendor} className="card mb-4 grid gap-3 p-5 sm:grid-cols-2">
            <h3 className="text-lg font-semibold sm:col-span-2">Edit vendor</h3>
            <Field label="Vendor name"><input className="input" name="name" defaultValue={editing.name} required /></Field>
            <Field label="New PIN (optional)"><input className="input" name="pin" inputMode="numeric" pattern="\d{6}" maxLength={6} /></Field>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" name="active" defaultChecked={editing.active} /> Active</label>
            <div className="flex gap-2"><button className="button">Save</button><button type="button" className="button-secondary" onClick={() => setEditing(null)}>Cancel</button></div>
          </form>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
        {items.map((vendor) => (
          <article className="card p-5" key={vendor.id}>
            <div className="flex justify-between">
              <strong>{vendor.name}</strong>
              <StatusBadge status={vendor.active ? "active" : "disabled"} />
            </div>
            <p className="mt-2 text-xs text-black/45">
              Last login: {vendor.last_login_at ? new Date(vendor.last_login_at).toLocaleString() : "Never"}
            </p>
            <div className="mt-4 flex gap-2">
              <button className="button-secondary min-h-9 px-2" title="Edit vendor" onClick={() => setEditing(vendor)}><Edit3 size={15} /></button>
              <button className="button-secondary min-h-9 px-2" title={vendor.active ? "Disable vendor" : "Enable vendor"} onClick={() => void toggleVendor(vendor)}><Power size={15} /></button>
              <button className="button-secondary min-h-9 px-2 text-red-700" title="Delete vendor" onClick={() => void removeVendor(vendor)}><Trash2 size={15} /></button>
            </div>
          </article>
        ))}
        {!items.length && <Empty text="No vendors yet." />}
        </div>
      </div>
    </div>
  );
}
