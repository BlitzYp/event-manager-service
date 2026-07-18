"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Empty, Field } from "./AdminUi";
import { StatusBadge } from "./StatusBadge";
import type { Event, Vendor } from "./types";

export function VendorsPanel({ event, csrf }: { event: Event; csrf: string }) {
  const [items, setItems] = useState<Vendor[]>([]);
  const [error, setError] = useState("");
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
          </article>
        ))}
        {!items.length && <Empty text="No vendors yet." />}
      </div>
    </div>
  );
}
