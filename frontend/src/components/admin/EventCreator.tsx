"use client";

import { type FormEvent, useState } from "react";
import { CalendarPlus } from "lucide-react";
import { api } from "@/lib/api";
import { Field } from "./AdminUi";

export function EventCreator({
  csrf,
  onCreated,
  embedded = false,
}: {
  csrf: string;
  onCreated: () => Promise<void>;
  embedded?: boolean;
}) {
  const [open, setOpen] = useState(embedded);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setError("");
    try {
      await api(
        "/admin/events",
        {
          method: "POST",
          body: JSON.stringify({
            code: form.get("code"),
            name: form.get("name"),
            status: form.get("status"),
            mode: form.get("mode"),
            currency: form.get("currency"),
            default_balance_minor: Math.round(Number(form.get("balance")) * 100),
            qr_ttl_seconds: 60,
            approval_required: form.get("approval") === "on",
            pending_payment_minutes: 5,
          }),
        },
        csrf,
      );
      formElement.reset();
      if (!embedded) setOpen(false);
      await onCreated();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not create event.");
    }
  }

  return (
    <section className={embedded ? "" : "mt-6"}>
      {!embedded && (
        <button className="button" onClick={() => setOpen(!open)}>
          <CalendarPlus size={18} /> New event
        </button>
      )}
      {open && (
        <form onSubmit={submit} className={`card grid gap-4 p-5 ${embedded ? "" : "mt-4 md:grid-cols-3"}`}>
          <h2 className={`text-xl font-semibold ${embedded ? "" : "md:col-span-3"}`}>New event</h2>
          <Field label="Event name">
            <input className="input" name="name" required />
          </Field>
          <Field label="Event code">
            <input className="input" name="code" pattern="[A-Za-z0-9_-]{2,50}" required />
          </Field>
          <Field label="State">
            <select className="input" name="status">
              <option value="draft">Draft</option>
              <option value="active">Active</option>
            </select>
          </Field>
          <Field label="Mode">
            <select className="input" name="mode">
              <option value="both">Money and coupons</option>
              <option value="money">Money</option>
              <option value="coupons">Coupons</option>
            </select>
          </Field>
          <Field label="Currency">
            <input className="input" name="currency" defaultValue="EUR" maxLength={3} />
          </Field>
          <Field label="Default balance">
            <input className="input" name="balance" type="number" min="0" step="0.01" defaultValue="50.00" />
          </Field>
          <label className="flex items-center gap-2 text-sm font-semibold">
            <input name="approval" type="checkbox" defaultChecked /> Participant approves payments
          </label>
          <div className={embedded ? "" : "md:col-span-2 flex justify-end gap-2"}>
            {!embedded && (
              <button type="button" className="button-secondary" onClick={() => setOpen(false)}>
                Cancel
              </button>
            )}
            <button className={`button ${embedded ? "w-full" : ""}`}>Create event</button>
          </div>
          {error && <p className={`alert-error text-sm ${embedded ? "" : "md:col-span-3"}`}>{error}</p>}
        </form>
      )}
    </section>
  );
}
