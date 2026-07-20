"use client";

import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  CircleAlert,
  Edit3,
  ExternalLink,
  Filter,
  KeyRound,
  Plus,
  Power,
  RotateCcw,
  Trash2,
  Upload,
  X,
  Zap,
} from "lucide-react";
import { api, money } from "@/lib/api";
import { Empty, Field } from "./AdminUi";
import { StatusBadge } from "./StatusBadge";
import type { Event, Participant, ScheduledAction } from "./types";

type ParticipantFilters = {
  search: string;
  group: string;
  wallet_status: "" | "active" | "suspended";
};

const emptyFilters: ParticipantFilters = { search: "", group: "", wallet_status: "" };

export function ParticipantsPanel({ event, csrf }: { event: Event; csrf: string }) {
  const [items, setItems] = useState<Participant[]>([]);
  const [groups, setGroups] = useState<string[]>([]);
  const [actions, setActions] = useState<ScheduledAction[]>([]);
  const [actionsLoaded, setActionsLoaded] = useState(false);
  const [hasAutomations, setHasAutomations] = useState(false);
  const [draftFilters, setDraftFilters] = useState(emptyFilters);
  const [appliedFilters, setAppliedFilters] = useState(emptyFilters);
  const [selectedWalletIds, setSelectedWalletIds] = useState<Set<number>>(new Set());
  const [editing, setEditing] = useState<Participant>();
  const [bulkActionId, setBulkActionId] = useState("");
  const [bulkOperation, setBulkOperation] = useState<"execute" | "include" | "exclude">("execute");
  const [bulkScope, setBulkScope] = useState<"selected" | "filtered">("filtered");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const bulkRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    const query = new URLSearchParams();
    if (appliedFilters.search) query.set("search", appliedFilters.search);
    if (appliedFilters.group) query.set("group", appliedFilters.group);
    if (appliedFilters.wallet_status) query.set("wallet_status", appliedFilters.wallet_status);
    const suffix = query.size ? `?${query}` : "";
    const result = await api<{ participants: Participant[]; groups: string[] }>(
      `/admin/events/${event.id}/participants${suffix}`,
    );
    setItems(result.participants);
    setGroups(result.groups);
    setSelectedWalletIds(new Set());
  }, [appliedFilters, event.id]);

  const loadActions = useCallback(async () => {
    const result = await api<{ actions: ScheduledAction[] }>(`/admin/events/${event.id}/actions`);
    setHasAutomations(result.actions.length > 0);
    setActions(result.actions.filter((action) => action.enabled && !action.completed_at));
    setActionsLoaded(true);
  }, [event.id]);

  useEffect(() => {
    void load();
    void loadActions();
  }, [load, loadActions]);

  async function create(submitEvent: FormEvent<HTMLFormElement>) {
    submitEvent.preventDefault();
    setError("");
    const formElement = submitEvent.currentTarget;
    const form = new FormData(formElement);
    try {
      const result = await api<{ wallet_link: string }>(
        `/admin/events/${event.id}/participants`,
        {
          method: "POST",
          body: JSON.stringify({
            participant_code: form.get("code"),
            name: form.get("name"),
            group: form.get("group") || null,
            email: form.get("email") || null,
          }),
        },
        csrf,
      );
      setNotice(`Wallet link (shown once): ${result.wallet_link}`);
      formElement.reset();
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Create failed.");
    }
  }

  async function saveParticipant(submitEvent: FormEvent<HTMLFormElement>) {
    submitEvent.preventDefault();
    if (!editing) return;
    const form = new FormData(submitEvent.currentTarget);
    setError("");
    try {
      await api(
        `/admin/events/${event.id}/participants/${editing.id}`,
        {
          method: "PUT",
          body: JSON.stringify({
            participant_code: form.get("participant_code"),
            name: form.get("name"),
            group: form.get("group") || null,
            email: form.get("email") || null,
          }),
        },
        csrf,
      );
      setEditing(undefined);
      setNotice("Participant updated.");
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Update failed.");
    }
  }

  async function deleteParticipant(participant: Participant) {
    if (!window.confirm(`Delete ${participant.name}? Participants with audit history cannot be deleted.`)) return;
    setError("");
    try {
      await api(
        `/admin/events/${event.id}/participants/${participant.id}`,
        { method: "DELETE" },
        csrf,
      );
      setNotice(`${participant.name} was deleted.`);
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Delete failed.");
    }
  }

  async function setWalletEnabled(participant: Participant) {
    setError("");
    try {
      await api(
        `/admin/events/${event.id}/wallets/${participant.wallet.id}/enabled?enabled=${!participant.wallet.enabled}`,
        { method: "PATCH" },
        csrf,
      );
      setNotice(`${participant.name}'s wallet was ${participant.wallet.enabled ? "suspended" : "activated"}.`);
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Wallet update failed.");
    }
  }

  async function openWallet(participant: Participant) {
    setError("");
    const previewWindow = window.open("", "_blank");
    if (previewWindow) {
      previewWindow.opener = null;
      previewWindow.document.title = "Opening wallet…";
      previewWindow.document.body.textContent = "Opening secure wallet preview…";
    }
    try {
      const result = await api<{ wallet_link: string }>(
        `/admin/events/${event.id}/participants/${participant.id}/wallet-preview`,
        { method: "POST" },
        csrf,
      );
      if (previewWindow) previewWindow.location.replace(result.wallet_link);
      else setNotice(`Preview link (expires shortly): ${result.wallet_link}`);
    } catch (failure) {
      previewWindow?.close();
      setError(failure instanceof Error ? failure.message : "Could not open wallet preview.");
    }
  }

  async function rotateWalletLink(participant: Participant) {
    setError("");
    try {
      const result = await api<{ wallet_link: string }>(
        `/admin/events/${event.id}/participants/${participant.id}/rotate-wallet-link`,
        { method: "POST" },
        csrf,
      );
      setNotice(`Replacement link (shown once): ${result.wallet_link}`);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not rotate wallet link.");
    }
  }

  async function importCsv(file: File) {
    const body = new FormData();
    body.append("file", file);
    setError("");
    try {
      const response = await api<Response>(
        `/admin/events/${event.id}/participants/import`,
        { method: "POST", body },
        csrf,
      );
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${event.code}-wallet-links.csv`;
      link.click();
      URL.revokeObjectURL(url);
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Import failed.");
    }
  }

  async function applyBulkAction() {
    const walletIds =
      bulkScope === "filtered"
        ? items.map((participant) => participant.wallet.id)
        : Array.from(selectedWalletIds);
    if (!bulkActionId) {
      setError("Choose an automation first.");
      return;
    }
    if (!walletIds.length) {
      setError(`There are no participants in the ${bulkScope} scope.`);
      return;
    }
    if (
      bulkOperation === "execute" &&
      !window.confirm(`Execute this automation for ${walletIds.length} participant wallets now?`)
    ) {
      return;
    }
    setError("");
    try {
      const result = await api<{ message: string }>(
        `/admin/events/${event.id}/actions/${bulkActionId}/wallet-scope`,
        {
          method: "POST",
          body: JSON.stringify({ operation: bulkOperation, wallet_ids: walletIds }),
        },
        csrf,
      );
      setNotice(result.message);
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Bulk action failed.");
    }
  }

  function openIndividualAction(participant: Participant) {
    setSelectedWalletIds(new Set([participant.wallet.id]));
    setBulkScope("selected");
    bulkRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  const allVisibleSelected = items.length > 0 && items.every((item) => selectedWalletIds.has(item.wallet.id));

  return (
    <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
      <form onSubmit={create} className="card h-fit p-5">
        <h3 className="text-xl font-semibold">Add participant</h3>
        <Field label="Participant code"><input className="input" name="code" required /></Field>
        <Field label="Name"><input className="input" name="name" required /></Field>
        <Field label="Group"><input className="input" name="group" /></Field>
        <Field label="Email"><input className="input" name="email" type="email" /></Field>
        <button className="button mt-4 w-full"><Plus size={17} /> Create wallet</button>
        <label className="button-secondary mt-2 w-full cursor-pointer">
          <Upload size={17} /> Import CSV
          <input
            className="hidden"
            type="file"
            accept=".csv,text/csv"
            onChange={(changeEvent) =>
              changeEvent.target.files?.[0] && void importCsv(changeEvent.target.files[0])
            }
          />
        </label>
      </form>

      <div className="min-w-0">
        {notice && <div className="alert-success mb-4 break-all text-sm">{notice}</div>}
        {error && <div className="alert-error mb-4 text-sm">{error}</div>}

        {actionsLoaded && (hasAutomations ? (
          <div ref={bulkRef} className="card mb-4 p-4">
            <div className="mb-3 flex items-center gap-2">
              <Zap size={18} className="text-leaf-700" />
              <div>
                <h3 className="font-semibold">Participant automation</h3>
                <p className="text-xs text-black/45">Run or scope an existing automation against this participant filter.</p>
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-[1fr_180px_190px_auto]">
              <select className="input" value={bulkActionId} onChange={(event) => setBulkActionId(event.target.value)}>
                <option value="">Choose automation</option>
                {actions.map((action) => <option key={action.id} value={action.id}>{action.name} · {action.action_type}</option>)}
              </select>
              <select className="input" value={bulkScope} onChange={(event) => setBulkScope(event.target.value as "selected" | "filtered")}>
                <option value="filtered">Filtered ({items.length})</option>
                <option value="selected">Selected ({selectedWalletIds.size})</option>
              </select>
              <select className="input" value={bulkOperation} onChange={(event) => setBulkOperation(event.target.value as "execute" | "include" | "exclude")}>
                <option value="execute">Execute now</option>
                <option value="include">Include in schedule</option>
                <option value="exclude">Exclude from schedule</option>
              </select>
              <button type="button" className="button" onClick={() => void applyBulkAction()} disabled={!actions.length}>
                <Zap size={16} /> Apply
              </button>
            </div>
            {!actions.length && <p className="mt-2 text-xs text-amber-700">Create an enabled automation before applying participant actions.</p>}
          </div>
        ) : (
          <div ref={bulkRef} className="alert-warning mb-4 flex items-center gap-3 text-sm" role="alert">
            <CircleAlert className="shrink-0" size={20} aria-hidden="true" />
            <p>No automations have been created. Create one to use participant actions.</p>
          </div>
        ))}

        <form
          className="card mb-4 grid gap-3 p-4 md:grid-cols-[minmax(0,1fr)_220px_180px_auto]"
          onSubmit={(submitEvent) => {
            submitEvent.preventDefault();
            setAppliedFilters(draftFilters);
          }}
        >
          <input
            className="input"
            placeholder="Search name, code, or group"
            value={draftFilters.search}
            onChange={(event) => setDraftFilters({ ...draftFilters, search: event.target.value })}
          />
          <select className="input" value={draftFilters.group} onChange={(event) => setDraftFilters({ ...draftFilters, group: event.target.value })}>
            <option value="">All groups</option>
            {groups.map((group) => <option key={group} value={group}>{group}</option>)}
          </select>
          <select
            className="input"
            value={draftFilters.wallet_status}
            onChange={(event) => setDraftFilters({ ...draftFilters, wallet_status: event.target.value as ParticipantFilters["wallet_status"] })}
          >
            <option value="">All statuses</option>
            <option value="active">Active</option>
            <option value="suspended">Suspended</option>
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
        </form>

        {editing && (
          <form onSubmit={saveParticipant} className="card mb-4 grid gap-3 p-5 md:grid-cols-2">
            <div className="flex items-center justify-between md:col-span-2">
              <h3 className="text-lg font-semibold">Edit participant</h3>
              <button type="button" className="button-secondary min-h-9 px-3" onClick={() => setEditing(undefined)}><X size={16} /> Close</button>
            </div>
            <Field label="Participant code"><input className="input" name="participant_code" defaultValue={editing.participant_code} required /></Field>
            <Field label="Name"><input className="input" name="name" defaultValue={editing.name} required /></Field>
            <Field label="Group"><input className="input" name="group" defaultValue={editing.group ?? ""} /></Field>
            <Field label="Email"><input className="input" name="email" type="email" defaultValue={editing.email ?? ""} /></Field>
            <button className="button md:col-span-2">Save participant</button>
          </form>
        )}

        <div className="card overflow-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>
                  <input
                    type="checkbox"
                    aria-label="Select every filtered participant"
                    checked={allVisibleSelected}
                    onChange={(event) => setSelectedWalletIds(event.target.checked ? new Set(items.map((item) => item.wallet.id)) : new Set())}
                  />
                </th>
                <th>Participant</th>
                <th>Group</th>
                <th>Available</th>
                <th>Status</th>
                {event.mode !== "money" && <th>Coupons</th>}
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((participant) => (
                <tr key={participant.id}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Select ${participant.name}`}
                      checked={selectedWalletIds.has(participant.wallet.id)}
                      onChange={(event) => {
                        const next = new Set(selectedWalletIds);
                        if (event.target.checked) next.add(participant.wallet.id);
                        else next.delete(participant.wallet.id);
                        setSelectedWalletIds(next);
                      }}
                    />
                  </td>
                  <td>
                    <strong>{participant.name}</strong>
                    <div className="text-xs text-black/45">{participant.participant_code}{participant.email ? ` · ${participant.email}` : ""}</div>
                  </td>
                  <td>{participant.group || "—"}</td>
                  <td>{money(participant.wallet.balance_minor - participant.wallet.reserved_minor, event.currency)}</td>
                  <td><StatusBadge status={participant.wallet.enabled ? "active" : "suspended"} /></td>
                  {event.mode !== "money" && (
                    <td>
                      <strong>{participant.coupons.available} available</strong>
                      <div className="text-xs text-black/45">
                        {participant.coupons.redeemed} redeemed
                        {participant.coupons.disabled ? ` · ${participant.coupons.disabled} disabled` : ""}
                      </div>
                    </td>
                  )}
                  <td>
                    <div className="flex items-center gap-1">
                      <button className="button-secondary min-h-9 px-2" type="button" title="Edit participant" onClick={() => setEditing(participant)}><Edit3 size={15} /></button>
                      <button className="button-secondary min-h-9 px-2" type="button" title="Open wallet preview" onClick={() => void openWallet(participant)}><ExternalLink size={15} /></button>
                      <button className="button-secondary min-h-9 px-2" type="button" title="Participant automation" onClick={() => openIndividualAction(participant)}><Zap size={15} /></button>
                      <button className="button-secondary min-h-9 px-2" type="button" title="Rotate wallet link" onClick={() => void rotateWalletLink(participant)}><KeyRound size={15} /></button>
                      <button className="button-secondary min-h-9 px-2" type="button" title={participant.wallet.enabled ? "Suspend wallet" : "Activate wallet"} onClick={() => void setWalletEnabled(participant)}><Power size={15} /></button>
                      <button className="button-secondary min-h-9 px-2 text-red-700" type="button" title="Delete participant" onClick={() => void deleteParticipant(participant)}><Trash2 size={15} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!items.length && <Empty text="No participants match these filters." />}
        </div>
      </div>
    </div>
  );
}
