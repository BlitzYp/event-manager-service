"use client";

import type { Dispatch, SetStateAction } from "react";
import { Edit3, ExternalLink, KeyRound, Mail, Power, Trash2, Zap } from "lucide-react";
import { money } from "@/lib/api";
import { Empty } from "../AdminUi";
import { StatusBadge } from "../StatusBadge";
import type { Event, Participant } from "../types";

type ParticipantTableProps = {
  event: Event;
  items: Participant[];
  selectedWalletIds: Set<number>;
  allVisibleSelected: boolean;
  setSelectedWalletIds: Dispatch<SetStateAction<Set<number>>>;
  setEditing: (participant: Participant) => void;
  setEmailRecipients: (participants: Participant[]) => void;
  openWallet: (participant: Participant) => Promise<void>;
  openIndividualAction: (participant: Participant) => void;
  rotateWalletLink: (participant: Participant) => Promise<void>;
  setWalletEnabled: (participant: Participant) => Promise<void>;
  deleteParticipant: (participant: Participant) => Promise<void>;
};

/** Render filtered participants, wallet selection, and per-participant action buttons. */
export function ParticipantTable({
  event, items, selectedWalletIds, allVisibleSelected, setSelectedWalletIds,
  setEditing, setEmailRecipients, openWallet, openIndividualAction, rotateWalletLink,
  setWalletEnabled, deleteParticipant,
}: ParticipantTableProps) {
  return (
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
                  <button
                    className="button-secondary min-h-9 px-2"
                    type="button"
                    title={participant.email ? `Send email to ${participant.name}` : "Participant has no email address"}
                    aria-label={participant.email ? `Send email to ${participant.name}` : `Cannot email ${participant.name}: no email address`}
                    disabled={!participant.email}
                    onClick={() => setEmailRecipients([participant])}
                  >
                    <Mail size={15} />
                  </button>
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
  );
}
