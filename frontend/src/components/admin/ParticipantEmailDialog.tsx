"use client";

import { type FormEvent, useEffect, useState } from "react";
import { Mail, Send, X } from "lucide-react";
import { api } from "@/lib/api";
import { EmailContentFields } from "./EmailContentFields";
import type { EmailTemplate, Event, Participant } from "./types";

export function ParticipantEmailDialog({
  event,
  csrf,
  recipients,
  onClose,
  onSent,
}: {
  event: Event;
  csrf: string;
  recipients: Participant[];
  onClose: () => void;
  onSent: (message: string) => void;
}) {
  const [templates, setTemplates] = useState<EmailTemplate[]>([]);
  const [developmentMode, setDevelopmentMode] = useState(false);
  const [testRecipient, setTestRecipient] = useState<string | null>(null);
  const [deliveryLimit, setDeliveryLimit] = useState(3);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  const deliverableCount = recipients.filter((participant) => participant.email).length;
  const missingEmailCount = recipients.length - deliverableCount;

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);

    void Promise.all([
      api<{ templates: EmailTemplate[] }>(`/admin/events/${event.id}/email-templates`),
      api<{
        development_mode: boolean;
        test_recipient?: string | null;
        development_delivery_limit: number;
      }>(`/admin/events/${event.id}/email-deliveries`),
    ])
      .then(([templateResult, deliveryResult]) => {
        setTemplates(templateResult.templates.filter((template) => !template.archived_at));
        setDevelopmentMode(deliveryResult.development_mode);
        setTestRecipient(deliveryResult.test_recipient ?? null);
        setDeliveryLimit(deliveryResult.development_delivery_limit);
      })
      .catch((failure) => {
        setError(failure instanceof Error ? failure.message : "Email settings could not be loaded.");
      })
      .finally(() => setLoading(false));

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [event.id, onClose]);

  async function sendEmail(submitEvent: FormEvent<HTMLFormElement>) {
    submitEvent.preventDefault();
    if (
      deliverableCount > 1 &&
      !window.confirm(`Send this email to ${deliverableCount} participants?`)
    ) {
      return;
    }

    const form = new FormData(submitEvent.currentTarget);
    const source = String(form.get("source") || "template");
    setError("");
    setSending(true);
    try {
      const result = await api<{
        sent: number;
        failed: number;
        simulated: number;
        skipped: number;
      }>(
        `/admin/events/${event.id}/emails/send`,
        {
          method: "POST",
          body: JSON.stringify({
            source,
            template_id: source === "template" ? Number(form.get("template_id")) : null,
            subject: form.get("subject") || null,
            body: source === "basic" ? form.get("body") : null,
            participant_ids: recipients.map((participant) => participant.id),
          }),
        },
        csrf,
      );
      onSent(
        `Sent: ${result.sent}; simulated: ${result.simulated}; without email: ${result.skipped}; failed: ${result.failed}.`,
      );
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Email send failed.");
      setSending(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        className="card max-h-[90vh] w-full max-w-xl overflow-auto p-5 shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="participant-email-title"
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-2">
            <Mail className="text-leaf-700" size={20} />
            <div>
              <h3 id="participant-email-title" className="text-xl font-semibold">
                {recipients.length === 1 ? "Email participant" : "Email filtered participants"}
              </h3>
              <p className="text-sm text-black/50">
                {deliverableCount} recipient{deliverableCount === 1 ? "" : "s"} with an email
                {missingEmailCount ? ` · ${missingEmailCount} without email will be skipped` : ""}
              </p>
            </div>
          </div>
          <button
            className="button-secondary min-h-9 px-2"
            type="button"
            title="Close"
            aria-label="Close email dialog"
            onClick={onClose}
          >
            <X size={17} />
          </button>
        </div>

        <div className="mt-4 max-h-32 overflow-auto rounded border border-black/10 bg-black/[0.02]">
          {recipients.slice(0, 8).map((participant) => (
            <div key={participant.id} className="flex justify-between gap-3 border-b border-black/5 px-3 py-2 text-sm last:border-0">
              <strong>{participant.name}</strong>
              <span className={participant.email ? "text-black/50" : "text-black/35"}>
                {participant.email || "No email"}
              </span>
            </div>
          ))}
          {recipients.length > 8 && (
            <p className="px-3 py-2 text-xs text-black/45">And {recipients.length - 8} more…</p>
          )}
        </div>

        {developmentMode && (
          <div className="alert-warning mt-4 text-sm">
            {testRecipient
              ? `Development mode: at most ${deliveryLimit} messages will be delivered to ${testRecipient}; the rest are simulated.`
              : "Development mode: messages will be simulated."}
          </div>
        )}
        {error && <div className="alert-error mt-4 text-sm">{error}</div>}

        <form className="mt-1" onSubmit={sendEmail}>
          <EmailContentFields
            eventId={event.id}
            templates={templates}
            disabled={sending}
            loading={loading}
          />
          <div className="mt-5 flex justify-end gap-2">
            <button className="button-secondary" type="button" onClick={onClose} disabled={sending}>
              Cancel
            </button>
            <button
              className="button"
              disabled={loading || sending || !deliverableCount}
            >
              <Send size={16} />
              {sending ? "Sending…" : `Send to ${deliverableCount}`}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
