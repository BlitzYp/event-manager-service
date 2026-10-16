"use client";

import { CircleAlert, Filter, Mail, Plus, RotateCcw, Upload, X, Zap } from "lucide-react";
import { Field } from "./AdminUi";
import { ParticipantEmailDialog } from "./ParticipantEmailDialog";
import { ParticipantTable } from "./participants/ParticipantTable";
import { emptyFilters, useParticipants, type ParticipantFilters } from "./participants/useParticipants";
import type { Event } from "./types";

/** Assemble participant forms, filters, email dialogs, and automation controls. */
export function ParticipantsPanel({ event, csrf }: { event: Event; csrf: string }) {
  const {
    items, groups, actions, actionsLoaded, hasAutomations,
    draftFilters, setDraftFilters, setAppliedFilters, selectedWalletIds, setSelectedWalletIds,
    editing, setEditing, bulkActionId, setBulkActionId, bulkOperation, setBulkOperation,
    bulkScope, setBulkScope, notice, setNotice, error, emailRecipients, setEmailRecipients, bulkRef,
    create, saveParticipant, deleteParticipant, setWalletEnabled, openWallet,
    rotateWalletLink, importCsv, applyBulkAction, openIndividualAction, allVisibleSelected
  } = useParticipants(event, csrf);

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
            <button
              className="button-secondary whitespace-nowrap px-3"
              type="button"
              title={items.some((participant) => participant.email) ? `Email all ${items.length} filtered participants` : "No filtered participants have an email address"}
              disabled={!items.some((participant) => participant.email)}
              onClick={() => setEmailRecipients(items)}
            >
              <Mail size={17} /> Email
            </button>
          </div>
        </form>

        {emailRecipients && (
          <ParticipantEmailDialog
            event={event}
            csrf={csrf}
            recipients={emailRecipients}
            onClose={() => setEmailRecipients(undefined)}
            onSent={(message) => {
              setEmailRecipients(undefined);
              setNotice(message);
            }}
          />
        )}

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

        <ParticipantTable
          event={event}
          items={items}
          selectedWalletIds={selectedWalletIds}
          allVisibleSelected={allVisibleSelected}
          setSelectedWalletIds={setSelectedWalletIds}
          setEditing={setEditing}
          setEmailRecipients={setEmailRecipients}
          openWallet={openWallet}
          openIndividualAction={openIndividualAction}
          rotateWalletLink={rotateWalletLink}
          setWalletEnabled={setWalletEnabled}
          deleteParticipant={deleteParticipant}
        />
      </div>
    </div>
  );
}
