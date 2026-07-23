"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";
import {
  Archive,
  Edit3,
  ImagePlus,
  Mail,
  Plus,
  RefreshCw,
  RotateCcw,
  Send,
  Trash2,
} from "lucide-react";
import { api } from "@/lib/api";
import { Empty, Field } from "./AdminUi";
import { EmailBuilder } from "./EmailBuilder";
import { EmailContentFields } from "./EmailContentFields";
import { StatusBadge } from "./StatusBadge";
import type {
  EmailAsset,
  EmailDelivery,
  EmailDocument,
  EmailTemplate,
  Event,
  Participant,
} from "./types";

type SendScope = "single" | "selected" | "all" | "group";

export function EmailsPanel({ event, csrf }: { event: Event; csrf: string }) {
  const [templates, setTemplates] = useState<EmailTemplate[]>([]);
  const [assets, setAssets] = useState<EmailAsset[]>([]);
  const [deliveries, setDeliveries] = useState<EmailDelivery[]>([]);
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [groups, setGroups] = useState<string[]>([]);
  const [editing, setEditing] = useState<EmailTemplate | null | undefined>();
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [scope, setScope] = useState<SendScope>("single");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [developmentMode, setDevelopmentMode] = useState(false);
  const [testRecipient, setTestRecipient] = useState<string | null>(null);
  const [deliveryLimit, setDeliveryLimit] = useState(3);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [templateResult, assetResult, deliveryResult, participantResult] = await Promise.all([
      api<{ templates: EmailTemplate[] }>(
        `/admin/events/${event.id}/email-templates?include_archived=${includeArchived}`,
      ),
      api<{ assets: EmailAsset[] }>(`/admin/events/${event.id}/email-assets`),
      api<{
        deliveries: EmailDelivery[];
        development_mode: boolean;
        test_recipient?: string | null;
        development_delivery_limit: number;
      }>(`/admin/events/${event.id}/email-deliveries`),
      api<{ participants: Participant[]; groups: string[] }>(
        `/admin/events/${event.id}/participants`,
      ),
    ]);
    setTemplates(templateResult.templates);
    setAssets(assetResult.assets);
    setDeliveries(deliveryResult.deliveries);
    setDevelopmentMode(deliveryResult.development_mode);
    setTestRecipient(deliveryResult.test_recipient ?? null);
    setDeliveryLimit(deliveryResult.development_delivery_limit);
    setParticipants(participantResult.participants);
    setGroups(participantResult.groups);
  }, [event.id, includeArchived]);

  useEffect(() => {
    void load().catch((failure) =>
      setError(failure instanceof Error ? failure.message : "Email data could not be loaded."),
    );
  }, [load]);

  async function editTemplate(row: EmailTemplate) {
    setError("");
    try {
      const result = await api<{ template: EmailTemplate }>(
        `/admin/events/${event.id}/email-templates/${row.id}`,
      );
      setEditing(result.template);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Template could not be opened.");
    }
  }

  async function saveTemplate(value: {
    name: string;
    subject: string;
    document: EmailDocument;
    rendered_html: string;
    version?: number;
  }) {
    const path = editing
      ? `/admin/events/${event.id}/email-templates/${editing.id}`
      : `/admin/events/${event.id}/email-templates`;
    const result = await api<{ template: EmailTemplate }>(
      path,
      {
        method: editing ? "PUT" : "POST",
        body: JSON.stringify(value),
      },
      csrf,
    );
    setNotice(editing ? "Email template updated." : "Email template created.");
    setEditing(result.template);
    await load();
  }

  async function archiveTemplate(row: EmailTemplate) {
    const archived = !row.archived_at;
    setError("");
    try {
      await api(
        `/admin/events/${event.id}/email-templates/${row.id}/archive`,
        { method: "PATCH", body: JSON.stringify({ archived }) },
        csrf,
      );
      setNotice(archived ? "Template archived." : "Template restored.");
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Template could not be updated.");
    }
  }

  async function uploadAsset(file: File) {
    const body = new FormData();
    body.append("file", file);
    setError("");
    try {
      await api(
        `/admin/events/${event.id}/email-assets`,
        { method: "POST", body },
        csrf,
      );
      setNotice("Image uploaded.");
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Image upload failed.");
    }
  }

  async function deleteAsset(asset: EmailAsset) {
    if (!window.confirm(`Delete ${asset.original_name}?`)) return;
    setError("");
    try {
      await api(
        `/admin/events/${event.id}/email-assets/${asset.id}`,
        { method: "DELETE" },
        csrf,
      );
      setNotice("Image deleted.");
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Image could not be deleted.");
    }
  }

  async function sendEmail(submitEvent: FormEvent<HTMLFormElement>) {
    submitEvent.preventDefault();
    const form = new FormData(submitEvent.currentTarget);
    const source = String(form.get("source") || "template");
    const payload: Record<string, unknown> = {
      source,
      template_id: source === "template" ? Number(form.get("template_id")) : null,
      subject: form.get("subject") || null,
      body: source === "basic" ? form.get("body") : null,
    };
    if (scope === "single") {
      payload.recipient_email = form.get("recipient_email");
      payload.recipient_name = form.get("recipient_name") || null;
    } else if (scope === "selected") {
      payload.participant_ids = Array.from(selectedIds);
    } else if (scope === "all") {
      payload.all_participants = true;
    } else {
      payload.group = form.get("group");
    }
    const approximateCount =
      scope === "selected"
        ? selectedIds.size
        : scope === "all"
          ? participants.length
          : scope === "group"
            ? participants.filter((participant) => participant.group === form.get("group")).length
            : 1;
    if (
      approximateCount > 1 &&
      !window.confirm(`Send this email to approximately ${approximateCount} recipients?`)
    )
      return;
    setError("");
    try {
      const result = await api<{
        sent: number;
        failed: number;
        simulated: number;
        skipped: number;
      }>(
        `/admin/events/${event.id}/emails/send`,
        { method: "POST", body: JSON.stringify(payload) },
        csrf,
      );
      setNotice(
        `Sent: ${result.sent}; simulated: ${result.simulated}; without email: ${result.skipped}; failed: ${result.failed}.`,
      );
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Email send failed.");
    }
  }

  if (editing !== undefined) {
    return (
      <EmailBuilder
        key={editing?.id ?? "new"}
        template={editing ?? undefined}
        assets={assets}
        onSave={saveTemplate}
        onClose={() => setEditing(undefined)}
      />
    );
  }

  const activeTemplates = templates.filter((template) => !template.archived_at);
  return (
    <div className="grid gap-6">
      {developmentMode && (
        <div className="alert-warning text-sm">
          {testRecipient
            ? `Development mode: at most ${deliveryLimit} messages per send are delivered to ${testRecipient}; the rest are simulated.`
            : "Development mode: messages are simulated. Set EMAIL_TEST_RECIPIENT to deliver limited test messages."}
        </div>
      )}
      {notice && <div className="alert-success text-sm">{notice}</div>}
      {error && <div className="alert-error text-sm">{error}</div>}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <section className="card overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 p-5">
            <div>
              <h3 className="text-xl font-semibold">Email templates</h3>
              <p className="text-sm text-black/45">Reusable visual templates scoped to this event.</p>
            </div>
            <div className="flex gap-2">
              <label className="button-secondary cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeArchived}
                  onChange={(changeEvent) => setIncludeArchived(changeEvent.target.checked)}
                />
                Archived
              </label>
              <button className="button" onClick={() => setEditing(null)}>
                <Plus size={16} /> New template
              </button>
            </div>
          </div>
          <div className="overflow-auto">
            <table className="data-table">
              <thead><tr><th>Name</th><th>Subject</th><th>Version</th><th>Status</th><th>Actions</th></tr></thead>
              <tbody>
                {templates.map((template) => (
                  <tr key={template.id}>
                    <td><strong>{template.name}</strong></td>
                    <td>{template.subject}</td>
                    <td>v{template.version}</td>
                    <td><StatusBadge status={template.archived_at ? "archived" : "active"} /></td>
                    <td>
                      <div className="flex gap-1">
                        <button className="button-secondary min-h-9 px-2" title="Edit template" onClick={() => void editTemplate(template)}><Edit3 size={15} /></button>
                        <button className="button-secondary min-h-9 px-2" title={template.archived_at ? "Restore template" : "Archive template"} onClick={() => void archiveTemplate(template)}>{template.archived_at ? <RotateCcw size={15} /> : <Archive size={15} />}</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!templates.length && <Empty text="No email templates have been created." />}
          </div>
        </section>

        <section className="card p-5">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-xl font-semibold">Images</h3>
              <p className="text-sm text-black/45">JPEG, PNG, GIF, or WebP; up to 5 MB.</p>
            </div>
            <label className="button cursor-pointer px-3">
              <ImagePlus size={16} /> Upload
              <input className="hidden" type="file" accept="image/jpeg,image/png,image/gif,image/webp" onChange={(changeEvent) => changeEvent.target.files?.[0] && void uploadAsset(changeEvent.target.files[0])} />
            </label>
          </div>
          <div className="mt-4 grid max-h-80 gap-2 overflow-auto">
            {assets.map((asset) => (
              <div key={asset.id} className="flex items-center gap-3 rounded border border-black/10 p-2">
                <img src={asset.url} alt="" className="h-12 w-16 rounded object-cover" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold">{asset.original_name}</p>
                  <p className="text-xs text-black/45">{asset.width} × {asset.height}</p>
                </div>
                <button className="button-secondary min-h-9 px-2 text-red-700" title="Delete image" onClick={() => void deleteAsset(asset)}><Trash2 size={15} /></button>
              </div>
            ))}
            {!assets.length && <Empty text="No email images uploaded." />}
          </div>
        </section>
      </div>

      <form className="card p-5" onSubmit={sendEmail}>
        <div className="flex items-center gap-2"><Send className="text-leaf-700" size={20} /><h3 className="text-xl font-semibold">Send email</h3></div>
        <div className="mt-4 max-w-md">
          <Field label="Recipient scope">
            <select className="input" value={scope} onChange={(changeEvent) => setScope(changeEvent.target.value as SendScope)}>
              <option value="single">One email address</option>
              <option value="selected">Selected participants</option>
              <option value="all">All participants</option>
              <option value="group">One group</option>
            </select>
          </Field>
        </div>
        {scope === "single" && <div className="mt-3 grid gap-3 md:grid-cols-2"><Field label="Recipient email"><input className="input" type="email" name="recipient_email" required /></Field><Field label="Recipient name"><input className="input" name="recipient_name" /></Field></div>}
        {scope === "group" && <div className="mt-3 max-w-md"><Field label="Group"><select className="input" name="group" required><option value="">Choose group</option>{groups.map((group) => <option key={group}>{group}</option>)}</select></Field></div>}
        {scope === "selected" && (
          <div className="mt-4 max-h-64 overflow-auto rounded border border-black/10">
            {participants.map((participant) => (
              <label key={participant.id} className="flex cursor-pointer items-center gap-3 border-b border-black/5 px-3 py-2 last:border-0">
                <input type="checkbox" checked={selectedIds.has(participant.id)} onChange={(changeEvent) => { const next = new Set(selectedIds); if (changeEvent.target.checked) next.add(participant.id); else next.delete(participant.id); setSelectedIds(next); }} />
                <span className="flex-1 text-sm"><strong>{participant.name}</strong><span className="ml-2 text-black/45">{participant.email || "No email"}</span></span>
              </label>
            ))}
          </div>
        )}
        <EmailContentFields eventId={event.id} templates={activeTemplates} />
        <button className="button mt-4" disabled={scope === "selected" && !selectedIds.size}><Mail size={16} /> Send email</button>
      </form>

      <section className="card overflow-hidden">
        <div className="flex items-center justify-between p-5"><div><h3 className="text-xl font-semibold">Delivery history</h3><p className="text-sm text-black/45">The newest 500 attempts.</p></div><button className="button-secondary px-3" onClick={() => void load()}><RefreshCw size={16} /> Refresh</button></div>
        <div className="overflow-auto">
          <table className="data-table">
            <thead><tr><th>Time</th><th>Recipient</th><th>Subject</th><th>Status</th><th>Details</th></tr></thead>
            <tbody>{deliveries.map((delivery) => <tr key={delivery.id}><td>{new Date(delivery.created_at).toLocaleString()}</td><td><strong>{delivery.recipient_name || "—"}</strong><div className="text-xs text-black/45">{delivery.recipient_email}</div></td><td>{delivery.subject}</td><td><StatusBadge status={delivery.status} /></td><td className="max-w-72 truncate text-xs text-red-700" title={delivery.error || ""}>{delivery.error || "—"}</td></tr>)}</tbody>
          </table>
          {!deliveries.length && <Empty text="No email delivery attempts yet." />}
        </div>
      </section>
    </div>
  );
}
