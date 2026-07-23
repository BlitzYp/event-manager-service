"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Edit3, Play, Power, Trash2, X } from "lucide-react";
import { api } from "@/lib/api";
import { Empty, Field } from "./AdminUi";
import { StatusBadge } from "./StatusBadge";
import type { EmailTemplate, Event, ScheduledAction } from "./types";

export function ActionsPanel({ event, csrf }: { event: Event; csrf: string }) {
  const [items, setItems] = useState<ScheduledAction[]>([]);
  const [templates, setTemplates] = useState<EmailTemplate[]>([]);
  const [actionType, setActionType] = useState("create_wallets");
  const [scheduleType, setScheduleType] = useState<"once" | "daily">("once");
  const [executeAt, setExecuteAt] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [executionTime, setExecutionTime] = useState("");
  const [editing, setEditing] = useState<ScheduledAction>();
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    const [actionResult, templateResult] = await Promise.all([
      api<{ actions: ScheduledAction[] }>(`/admin/events/${event.id}/actions`),
      api<{ templates: EmailTemplate[] }>(`/admin/events/${event.id}/email-templates`),
    ]);
    setItems(actionResult.actions);
    setTemplates(templateResult.templates);
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

  function resetEditor() {
    const nextRun = new Date(Date.now() + 60 * 60 * 1000);
    setEditing(undefined);
    setScheduleType("once");
    setActionType("create_wallets");
    setExecuteAt(toLocalDateTimeValue(nextRun));
    setStartDate(toLocalDateValue(nextRun));
    setEndDate(toLocalDateValue(nextRun));
    setExecutionTime(toLocalTimeValue(nextRun));
  }

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

      const payload = {
        name: form.get("name"),
        action_type: form.get("action_type"),
        schedule_type: scheduleType,
        execute_at: parsedExecution.toISOString(),
        schedule_start: scheduleType === "daily" ? startDate : null,
        schedule_end: scheduleType === "daily" ? endDate : null,
        schedule_time: scheduleType === "daily" ? executionTime : null,
        auto_delete: form.get("auto_delete") === "on",
        excluded_wallet_ids: [],
        email_template_id:
          actionType === "send_email" ? Number(form.get("email_template_id")) : null,
        email_subject:
          actionType === "send_email" ? form.get("email_subject") || null : null,
      };
      await api(
        editing
          ? `/admin/events/${event.id}/actions/${editing.id}`
          : `/admin/events/${event.id}/actions`,
        {
          method: editing ? "PUT" : "POST",
          body: JSON.stringify(payload),
        },
        csrf,
      );
      setNotice(editing ? "Automation updated." : "Automation created.");
      formElement.reset();
      resetEditor();
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not create the schedule.");
    }
  }

  function editAction(action: ScheduledAction) {
    const execution = new Date(action.execute_at);
    setEditing(action);
    setActionType(action.action_type);
    setScheduleType(action.schedule_type as "once" | "daily");
    setExecuteAt(toLocalDateTimeValue(execution));
    setStartDate(action.schedule_start || toLocalDateValue(execution));
    setEndDate(action.schedule_end || action.schedule_start || toLocalDateValue(execution));
    setExecutionTime(action.schedule_time?.slice(0, 5) || toLocalTimeValue(execution));
    setError("");
    setNotice("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function toggleAction(action: ScheduledAction) {
    setError("");
    try {
      await api(
        `/admin/events/${event.id}/actions/${action.id}/enabled?enabled=${!action.enabled}`,
        { method: "PATCH" },
        csrf,
      );
      setNotice(action.enabled ? "Automation disabled." : "Automation enabled.");
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Automation status could not be changed.");
    }
  }

  async function deleteAction(action: ScheduledAction) {
    if (!window.confirm(`Delete automation “${action.name}”?`)) return;
    setError("");
    try {
      await api(
        `/admin/events/${event.id}/actions/${action.id}`,
        { method: "DELETE" },
        csrf,
      );
      setNotice("Automation deleted.");
      if (editing?.id === action.id) resetEditor();
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Automation could not be deleted.");
    }
  }

  async function runAction(action: ScheduledAction) {
    setError("");
    try {
      await api(`/admin/events/${event.id}/actions/${action.id}/run`, { method: "POST" }, csrf);
      setNotice("Automation executed.");
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Automation could not be executed.");
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
      <form key={editing?.id ?? "create"} onSubmit={submit} className="card h-fit p-5">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-xl font-semibold">{editing ? "Edit automation" : "Schedule action"}</h3>
          {editing && <button className="button-secondary min-h-9 px-2" type="button" title="Cancel editing" onClick={resetEditor}><X size={16} /></button>}
        </div>
        <Field label="Name"><input className="input" name="name" defaultValue={editing?.name ?? ""} required /></Field>
        <Field label="Action">
          <select className="input" name="action_type" value={actionType} onChange={(changeEvent) => setActionType(changeEvent.target.value)}>
            <option value="create_wallets">Create missing wallets</option>
            <option value="activate_wallets">Activate wallets</option>
            <option value="deactivate_wallets">Disable wallets</option>
            <option value="issue_coupons">Issue missing coupons</option>
            <option value="refill_coupons">Refill redeemed coupons</option>
            <option value="disable_coupons">Disable coupons</option>
            <option value="enable_coupons">Enable coupons</option>
            <option value="delete_wallets">Delete empty wallets</option>
            <option value="send_email">Send email</option>
          </select>
        </Field>
        {actionType === "send_email" && (
          <>
            <Field label="Email template">
              <select className="input" name="email_template_id" defaultValue={editing?.email_template_id ?? ""} required>
                <option value="">Choose template</option>
                {templates.map((template) => <option key={template.id} value={template.id}>{template.name}</option>)}
              </select>
            </Field>
            <Field label="Subject override (optional)"><input className="input" name="email_subject" defaultValue={editing?.email_subject ?? ""} /></Field>
            {!templates.length && <p className="alert-warning mt-3 text-sm">Create an email template before scheduling email delivery.</p>}
          </>
        )}
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
          <input type="checkbox" name="auto_delete" defaultChecked={editing?.auto_delete ?? false} /> Remove schedule after completion
        </label>
        {error && <p className="alert-error mt-4 text-sm">{error}</p>}
        <button className="button mt-4 w-full">{editing ? "Save automation" : "Create schedule"}</button>
      </form>
      <div className="space-y-3">
        {notice && <div className="alert-success text-sm">{notice}</div>}
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
            <div className="flex flex-wrap gap-2">
              <button className="button-secondary min-h-9 px-3" type="button" onClick={() => editAction(action)}><Edit3 size={15} /> Edit</button>
              <button className="button-secondary min-h-9 px-3" type="button" onClick={() => void toggleAction(action)}><Power size={15} /> {action.enabled ? "Disable" : "Enable"}</button>
              <button className="button-secondary min-h-9 px-3" type="button" onClick={() => void runAction(action)}><Play size={15} /> Run now</button>
              <button
                className="button-secondary min-h-9 px-3 text-red-700"
                type="button"
                title={action.run_count ? "Automations with execution history cannot be deleted; disable it instead." : "Delete automation"}
                disabled={action.run_count > 0}
                onClick={() => void deleteAction(action)}
              >
                <Trash2 size={15} /> Delete
              </button>
            </div>
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
