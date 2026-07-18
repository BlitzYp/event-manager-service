"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Empty, Field } from "./AdminUi";
import { StatusBadge } from "./StatusBadge";
import type { Event, ScheduledAction } from "./types";

export function ActionsPanel({ event, csrf }: { event: Event; csrf: string }) {
  const [items, setItems] = useState<ScheduledAction[]>([]);
  const [scheduleType, setScheduleType] = useState<"once" | "daily">("once");
  const [executeAt, setExecuteAt] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [executionTime, setExecutionTime] = useState("");
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    const result = await api<{ actions: ScheduledAction[] }>(`/admin/events/${event.id}/actions`);
    setItems(result.actions);
  }, [event.id]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const firstRun = new Date(Date.now() + 60 * 60 * 1000);
    setExecuteAt(toLocalDateTimeValue(firstRun));
    setStartDate(toLocalDateValue(firstRun));
    setEndDate(toLocalDateValue(firstRun));
    setExecutionTime(toLocalTimeValue(firstRun));
  }, []);

  async function submit(submitEvent: FormEvent<HTMLFormElement>) {
    submitEvent.preventDefault();
    const formElement = submitEvent.currentTarget;
    const form = new FormData(formElement);
    setError("");
    try {
      const localExecution = scheduleType === "daily" ? `${startDate}T${executionTime}` : executeAt;
      const parsedExecution = new Date(localExecution);
      if (!localExecution || Number.isNaN(parsedExecution.getTime())) {
        throw new Error("Choose a valid execution date and time.");
      }
      if (scheduleType === "daily" && endDate < startDate) {
        throw new Error("The final execution date cannot be before the first date.");
      }

      await api(
        `/admin/events/${event.id}/actions`,
        {
          method: "POST",
          body: JSON.stringify({
            name: form.get("name"),
            action_type: form.get("action_type"),
            schedule_type: scheduleType,
            execute_at: parsedExecution.toISOString(),
            schedule_start: scheduleType === "daily" ? startDate : null,
            schedule_end: scheduleType === "daily" ? endDate : null,
            schedule_time: scheduleType === "daily" ? executionTime : null,
            auto_delete: form.get("auto_delete") === "on",
            excluded_wallet_ids: [],
          }),
        },
        csrf,
      );
      formElement.reset();
      const nextRun = new Date(Date.now() + 60 * 60 * 1000);
      setScheduleType("once");
      setExecuteAt(toLocalDateTimeValue(nextRun));
      setStartDate(toLocalDateValue(nextRun));
      setEndDate(toLocalDateValue(nextRun));
      setExecutionTime(toLocalTimeValue(nextRun));
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not create the schedule.");
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
      <form onSubmit={submit} className="card p-5">
        <h3 className="text-xl font-semibold">Schedule action</h3>
        <Field label="Name"><input className="input" name="name" required /></Field>
        <Field label="Action">
          <select className="input" name="action_type">
            <option value="create_wallets">Create missing wallets</option>
            <option value="activate_wallets">Activate wallets</option>
            <option value="deactivate_wallets">Disable wallets</option>
            <option value="issue_coupons">Issue missing coupons</option>
            <option value="refill_coupons">Refill redeemed coupons</option>
            <option value="disable_coupons">Disable coupons</option>
            <option value="enable_coupons">Enable coupons</option>
            <option value="delete_wallets">Delete empty wallets</option>
          </select>
        </Field>
        <Field label="Frequency">
          <select
            className="input"
            name="schedule_type"
            value={scheduleType}
            onChange={(changeEvent) => setScheduleType(changeEvent.target.value as "once" | "daily")}
          >
            <option value="once">Once</option>
            <option value="daily">Daily</option>
          </select>
        </Field>
        {scheduleType === "once" ? (
          <Field label="Execution date and time">
            <input
              className="input"
              name="execute_at"
              type="datetime-local"
              value={executeAt}
              onChange={(changeEvent) => setExecuteAt(changeEvent.target.value)}
              required
            />
          </Field>
        ) : (
          <div className="mt-3 grid grid-cols-2 gap-3">
            <Field label="From date">
              <input
                className="input"
                name="schedule_start"
                type="date"
                value={startDate}
                onChange={(changeEvent) => setStartDate(changeEvent.target.value)}
                required
              />
            </Field>
            <Field label="Until date">
              <input
                className="input"
                name="schedule_end"
                type="date"
                min={startDate}
                value={endDate}
                onChange={(changeEvent) => setEndDate(changeEvent.target.value)}
                required
              />
            </Field>
            <div className="col-span-2">
              <Field label="Execution time">
                <input
                  className="input"
                  name="schedule_time"
                  type="time"
                  value={executionTime}
                  onChange={(changeEvent) => setExecutionTime(changeEvent.target.value)}
                  required
                />
              </Field>
            </div>
          </div>
        )}
        <label className="mt-3 flex items-center gap-2 text-sm">
          <input type="checkbox" name="auto_delete" /> Remove schedule after completion
        </label>
        {error && <p className="alert-error mt-4 text-sm">{error}</p>}
        <button className="button mt-4 w-full">Create schedule</button>
      </form>
      <div className="space-y-3">
        {items.map((action) => (
          <article className="card flex flex-col justify-between gap-3 p-5 sm:flex-row sm:items-center" key={action.id}>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <strong>{action.name}</strong>
                <StatusBadge status={action.completed_at ? "completed" : action.enabled ? "scheduled" : "disabled"} />
              </div>
              <p className="text-sm text-black/45">
                {action.action_type} · {action.schedule_type} · {new Date(action.execute_at).toLocaleString()}
              </p>
              {action.schedule_type === "daily" && action.schedule_start && action.schedule_end && (
                <p className="mt-1 text-xs text-black/45">
                  Daily from {action.schedule_start} through {action.schedule_end} at {action.schedule_time?.slice(0, 5)}
                </p>
              )}
            </div>
            <button
              className="button-secondary min-h-9"
              onClick={async () => {
                await api(`/admin/events/${event.id}/actions/${action.id}/run`, { method: "POST" }, csrf);
                await load();
              }}
            >
              Run now
            </button>
          </article>
        ))}
        {!items.length && <Empty text="No scheduled actions yet." />}
      </div>
    </div>
  );
}

function pad(value: number) {
  return String(value).padStart(2, "0");
}

function toLocalDateValue(value: Date) {
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`;
}

function toLocalTimeValue(value: Date) {
  return `${pad(value.getHours())}:${pad(value.getMinutes())}`;
}

function toLocalDateTimeValue(value: Date) {
  return `${toLocalDateValue(value)}T${toLocalTimeValue(value)}`;
}
