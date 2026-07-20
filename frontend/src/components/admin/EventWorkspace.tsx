"use client";

import { useState } from "react";
import { CalendarRange, CheckCircle2, Clock3, Download, ShieldCheck, Ticket, Users, WalletCards } from "lucide-react";
import { AccountsPanel } from "./AccountsPanel";
import { ActionsPanel } from "./ActionsPanel";
import { CouponsPanel } from "./CouponsPanel";
import { EventsPanel } from "./EventsPanel";
import { ParticipantsPanel } from "./ParticipantsPanel";
import { StatusBadge } from "./StatusBadge";
import { TransactionsPanel } from "./TransactionsPanel";
import type { Event } from "./types";
import { VendorsPanel } from "./VendorsPanel";

type Tab = "events" | "accounts" | "participants" | "vendors" | "coupons" | "actions" | "transactions";

const tabs = [
  ["events", "Events", CalendarRange],
  ["accounts", "Admin accounts", ShieldCheck],
  ["participants", "Participants", Users],
  ["vendors", "Vendors", WalletCards],
  ["coupons", "Coupons", Ticket],
  ["actions", "Automation", Clock3],
  ["transactions", "Transactions", Download],
] as const;

export function EventWorkspace({
  event,
  events,
  csrf,
  onSelectEvent,
  onEventsChanged,
  isSuperAdmin,
  onImpersonated,
}: {
  event?: Event;
  events: Event[];
  csrf: string;
  onSelectEvent: (eventId: number) => void;
  onEventsChanged: () => Promise<void>;
  isSuperAdmin: boolean;
  onImpersonated: () => Promise<void>;
}) {
  const [tab, setTab] = useState<Tab>(event ? "participants" : "events");

  return (
    <section className="mt-6">
      {event && <div className="wallet-current-event mb-6">
        <div>
          <div className="mb-1 flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-[#245c18]">
            <CheckCircle2 size={15} /> Selected event
          </div>
          <h2 className="text-xl font-semibold">{event.name}</h2>
          <p className="mt-1 text-sm text-black/50">Code: {event.code} · Currency: {event.currency}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="badge bg-[#087f5b] text-white">{event.mode}</span>
          <StatusBadge status={event.status} />
        </div>
      </div>}

      <nav
        className="wallet-tabs mb-6"
        aria-label="Event sections"
        role="tablist"
      >
        {tabs.filter(([key]) => key !== "accounts" || isSuperAdmin).map(([key, label, Icon]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            disabled={key !== "events" && key !== "accounts" && !event}
            role="tab"
            aria-selected={tab === key}
          >
            <Icon size={16} /> {label}
          </button>
        ))}
      </nav>

      {tab === "events" && (
        <EventsPanel
          events={events}
          selectedEventId={event?.id}
          csrf={csrf}
          onSelect={onSelectEvent}
          onChanged={onEventsChanged}
        />
      )}
      {tab === "accounts" && isSuperAdmin && (
        <AccountsPanel csrf={csrf} onImpersonated={onImpersonated} />
      )}
      {tab === "participants" && event && <ParticipantsPanel event={event} csrf={csrf} />}
      {tab === "vendors" && event && <VendorsPanel event={event} csrf={csrf} />}
      {tab === "coupons" && event && <CouponsPanel event={event} csrf={csrf} />}
      {tab === "actions" && event && <ActionsPanel event={event} csrf={csrf} />}
      {tab === "transactions" && event && <TransactionsPanel event={event} />}
    </section>
  );
}
