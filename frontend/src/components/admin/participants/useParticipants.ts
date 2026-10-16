"use client";

import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { Event, Participant, ScheduledAction } from "../types";

export type ParticipantFilters = {
  search: string;
  group: string;
  wallet_status: "" | "active" | "suspended";
};

export const emptyFilters: ParticipantFilters = { search: "", group: "", wallet_status: "" };

/** Load event participants and expose form, wallet, CSV, selection, and automation handlers. */
export function useParticipants(event: Event, csrf: string) {
  // Server-loaded event records and automation availability.
  const [items, setItems] = useState<Participant[]>([]);
  const [groups, setGroups] = useState<string[]>([]);
  const [actions, setActions] = useState<ScheduledAction[]>([]);
  const [actionsLoaded, setActionsLoaded] = useState(false);
  const [hasAutomations, setHasAutomations] = useState(false);
  // Draft filters only affect results after Apply; selection belongs to the loaded list.
  const [draftFilters, setDraftFilters] = useState(emptyFilters);
  const [appliedFilters, setAppliedFilters] = useState(emptyFilters);
  const [selectedWalletIds, setSelectedWalletIds] = useState<Set<number>>(new Set());
  const [editing, setEditing] = useState<Participant>();
  // Automation target and operation chosen in the bulk-action controls.
  const [bulkActionId, setBulkActionId] = useState("");
  const [bulkOperation, setBulkOperation] = useState<"execute" | "include" | "exclude">("execute");
  const [bulkScope, setBulkScope] = useState<"selected" | "filtered">("filtered");
  // Feedback, email dialog recipients, and the automation scroll target.
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [emailRecipients, setEmailRecipients] = useState<Participant[]>();
  const bulkRef = useRef<HTMLDivElement>(null);

  /** Load the applied event filters and clear wallet selection after each list refresh. */
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

  /**
   * Load usable automations for this event and distinguish no automations from disabled/completed ones.
   */
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

  /**
   * Create a participant wallet, show its one-time secret link, reset the form, and reload participants.
   */
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

  /** Save participant edits and reload the filtered list after closing the editor. */
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

  /** Confirm participant deletion and surface server protection for immutable audit history. */
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

  /** Activate or suspend one participant wallet and refresh its displayed availability. */
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

  /** Open a short-lived secure preview in a new tab without rotating the participant access link. */
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

  /** Revoke old participant links and show the replacement secret URL once. */
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

  /** Upload participant CSV, download the one-time wallet-link CSV, and refresh participants. */
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

  /** Execute or scope an automation against the selected or filtered event-wallet IDs. */
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

  /** Select one participant wallet and scroll to its automation controls. */
  function openIndividualAction(participant: Participant) {
    setSelectedWalletIds(new Set([participant.wallet.id]));
    setBulkScope("selected");
    bulkRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  const allVisibleSelected = items.length > 0 && items.every((item) => selectedWalletIds.has(item.wallet.id));

  return {
    items, groups, actions, actionsLoaded, hasAutomations,
    draftFilters, setDraftFilters, setAppliedFilters, selectedWalletIds, setSelectedWalletIds,
    editing, setEditing, bulkActionId, setBulkActionId, bulkOperation, setBulkOperation,
    bulkScope, setBulkScope, notice, setNotice, error, emailRecipients, setEmailRecipients, bulkRef,
    create, saveParticipant, deleteParticipant, setWalletEnabled, openWallet,
    rotateWalletLink, importCsv, applyBulkAction, openIndividualAction, allVisibleSelected
  };
}
