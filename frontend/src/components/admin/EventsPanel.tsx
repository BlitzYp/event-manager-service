"use client";

import { useState } from "react";
import { Archive, CheckCircle2, PlayCircle, RotateCcw, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { Empty } from "./AdminUi";
import { EventCreator } from "./EventCreator";
import { StatusBadge } from "./StatusBadge";
import type { Event } from "./types";

export function EventsPanel({
  events,
  selectedEventId,
  csrf,
  onSelect,
  onChanged,
}: {
  events: Event[];
  selectedEventId?: number;
  csrf: string;
  onSelect: (eventId: number) => void;
  onChanged: () => Promise<void>;
}) {
  const [busyId, setBusyId] = useState<number>();
  const [approvalOverride, setApprovalOverride] = useState<{
    eventId: number;
    value: boolean;
  }>();
  const [error, setError] = useState("");

  async function updateEvent(event: Event, changes: Partial<Event>, errorMessage: string) {
    setBusyId(event.id);
    setError("");
    try {
      await api(
        `/admin/events/${event.id}`,
        {
          method: "PUT",
          body: JSON.stringify({
            code: event.code,
            name: event.name,
            status: event.status,
            mode: event.mode,
            currency: event.currency,
            default_balance_minor: event.default_balance_minor,
            qr_ttl_seconds: event.qr_ttl_seconds,
            approval_required: event.approval_required,
            pending_payment_minutes: event.pending_payment_minutes,
            ...changes,
          }),
        },
        csrf,
      );
      await onChanged();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : errorMessage);
    } finally {
      setBusyId(undefined);
    }
  }

  async function setStatus(event: Event, status: Event["status"]) {
    await updateEvent(event, { status }, "Could not update the event.");
  }

  async function setApprovalRequired(event: Event, approvalRequired: boolean) {
    setApprovalOverride({ eventId: event.id, value: approvalRequired });
    setBusyId(event.id);
    setError("");
    try {
      await api(
        `/admin/events/${event.id}/approval`,
        {
          method: "PATCH",
          body: JSON.stringify({ approval_required: approvalRequired }),
        },
        csrf,
      );
      await onChanged();
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Could not update participant confirmation.",
      );
    } finally {
      setApprovalOverride(undefined);
      setBusyId(undefined);
    }
  }

  async function deleteEvent(event: Event) {
    if (!window.confirm(`Delete ${event.name}? This cannot be undone.`)) return;
    setBusyId(event.id);
    setError("");
    try {
      await api(`/admin/events/${event.id}`, { method: "DELETE" }, csrf);
      await onChanged();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not delete the event.");
    } finally {
      setBusyId(undefined);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
      <EventCreator csrf={csrf} onCreated={onChanged} embedded />

      <section className="card min-w-0 overflow-hidden">
        <div className="border-b border-black/10 px-5 py-4">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-xl font-semibold">Events</h3>
            <span className="badge bg-leaf-50 text-leaf-700">
              {events.filter((event) => event.status === "active").length} active
            </span>
          </div>
          <p className="mt-1 text-sm text-black/50">
            Multiple events can be active simultaneously. Selecting an event only chooses
            which one you are editing in this workspace.
          </p>
        </div>
        {error && <p className="alert-error m-4 text-sm">{error}</p>}
        {events.length ? (
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Event</th>
                  <th>Systems</th>
                  <th>Payment confirmation</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {events.map((event) => {
                  const selected = event.id === selectedEventId;
                  const nextStatus = event.status === "draft" ? "active" : event.status === "active" ? "archived" : "draft";
                  return (
                    <tr key={event.id}>
                      <td>
                        <strong>{event.name}</strong>
                        <br />
                        <small className="text-black/45">{event.code}</small>
                      </td>
                      <td className="capitalize">{event.mode === "both" ? "Money + coupons" : event.mode}</td>
                      <td>
                        <label className="inline-flex cursor-pointer items-center gap-2">
                          <input
                            className="peer sr-only"
                            type="checkbox"
                            role="switch"
                            checked={
                              approvalOverride?.eventId === event.id
                                ? approvalOverride.value
                                : event.approval_required
                            }
                            disabled={busyId === event.id}
                            onChange={(changeEvent) =>
                              void setApprovalRequired(event, changeEvent.target.checked)
                            }
                            aria-label={`Require participant confirmation for ${event.name}`}
                          />
                          <span className="relative h-6 w-11 shrink-0 rounded-full bg-black/20 transition-colors after:absolute after:left-1 after:top-1 after:h-4 after:w-4 after:rounded-full after:bg-white after:shadow after:transition-transform peer-checked:bg-leaf-600 peer-checked:after:translate-x-5 peer-disabled:cursor-wait peer-disabled:opacity-60 peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-leaf-600" />
                          <span className="text-sm font-medium">
                            {event.approval_required ? "Required" : "Automatic"}
                          </span>
                        </label>
                      </td>
                      <td>
                        <StatusBadge status={event.status} />
                      </td>
                      <td>
                        <div className="flex items-center gap-2">
                          <button
                            className={selected ? "button min-h-9 px-3" : "button-secondary min-h-9 px-3"}
                            type="button"
                            onClick={() => onSelect(event.id)}
                            disabled={selected}
                          >
                            {selected ? <CheckCircle2 size={15} /> : <PlayCircle size={15} />}
                            {selected ? "Selected" : "Manage"}
                          </button>
                          <button
                            className="button-secondary min-h-9 px-3"
                            type="button"
                            disabled={busyId === event.id}
                            onClick={() => void setStatus(event, nextStatus)}
                          >
                            {event.status === "draft" ? (
                              <PlayCircle size={15} />
                            ) : event.status === "active" ? (
                              <Archive size={15} />
                            ) : (
                              <RotateCcw size={15} />
                            )}
                            {event.status === "draft" ? "Activate" : event.status === "active" ? "Archive" : "Restore"}
                          </button>
                          <button
                            className="button-secondary min-h-9 px-3 text-red-700"
                            type="button"
                            disabled={busyId === event.id}
                            onClick={() => void deleteEvent(event)}
                            title="Delete event"
                          >
                            <Trash2 size={15} /> Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-5"><Empty text="No events have been created yet." /></div>
        )}
      </section>
    </div>
  );
}
