"use client";

import { useEffect, useRef, useState } from "react";
import { Bold, Eye, Italic, Link2, Underline, UserRound } from "lucide-react";
import { api } from "@/lib/api";
import { Field } from "./AdminUi";
import type { EmailTemplate } from "./types";

type EmailSource = "template" | "basic";

const sampleValues: Record<string, string> = {
  "{{participant_first_name}}": "Anna",
  "{{participant_last_name}}": "Bērziņa",
  "{{participant_name}}": "Anna Bērziņa",
  "{{participant_code}}": "P-1042",
  "{{participant_email}}": "anna@example.com",
  "{{participant_group}}": "Guests",
  "{{event_name}}": "Example event",
  "{{event_code}}": "EXAMPLE",
  "{{wallet_link}}": "https://example.com/wallet",
  "{{public_wallet}}": "https://example.com/wallet",
};

function sampleContent(value: string): string {
  let result = value;
  for (const [placeholder, sample] of Object.entries(sampleValues)) {
    result = result.replaceAll(placeholder, sample);
    const encoded = placeholder.slice(2, -2);
    result = result.replaceAll(`%7B%7B${encoded}%7D%7D`, sample);
  }
  return result;
}

function sanitizedBasicPreview(value: string): string {
  const source = new DOMParser().parseFromString(value, "text/html");
  const allowed = new Set(["A", "B", "STRONG", "I", "EM", "U", "SPAN", "P", "DIV", "BR"]);
  const colorPattern = /^(?:#[0-9a-f]{3}(?:[0-9a-f]{3})?|rgba?\([0-9.,\s]+\))$/i;

  function clean(node: Node): string {
    if (node.nodeType === Node.TEXT_NODE) {
      const span = document.createElement("span");
      span.textContent = node.textContent || "";
      return span.innerHTML;
    }
    if (!(node instanceof HTMLElement)) return "";
    if (node.tagName === "SCRIPT" || node.tagName === "STYLE") return "";
    const children = Array.from(node.childNodes).map(clean).join("");
    if (node.tagName === "FONT") {
      const color = node.getAttribute("color") || "";
      return colorPattern.test(color) ? `<span style="color:${color}">${children}</span>` : children;
    }
    if (!allowed.has(node.tagName)) return children;
    if (node.tagName === "BR") return "<br>";
    const tag = node.tagName.toLowerCase();
    if (tag === "a") {
      const href = node.getAttribute("href") || "";
      return ["{{wallet_link}}", "{{public_wallet}}"].includes(href)
        ? `<a href="${href}">${children}</a>`
        : children;
    }
    if (tag === "span") {
      const color = node.style.color;
      return colorPattern.test(color) ? `<span style="color:${color}">${children}</span>` : `<span>${children}</span>`;
    }
    return `<${tag}>${children}</${tag}>`;
  }

  return Array.from(source.body.childNodes).map(clean).join("");
}

function basicPreview(value: string): string {
  let content = sanitizedBasicPreview(value.trim());
  content = content.replace(
    /(?<!href=")\{\{(?:wallet_link|public_wallet)\}\}/g,
    (placeholder) => `<a href="${placeholder}">Open public wallet</a>`,
  );
  return sampleContent(
    `<div style="font-family:Arial,sans-serif;font-size:16px;line-height:1.6;color:#1f2937;white-space:pre-wrap">${content}</div>`,
  );
}

export function EmailContentFields({
  eventId,
  templates,
  disabled = false,
  loading = false,
}: {
  eventId: number;
  templates: EmailTemplate[];
  disabled?: boolean;
  loading?: boolean;
}) {
  const [source, setSource] = useState<EmailSource>("template");
  const [templateId, setTemplateId] = useState("");
  const [body, setBody] = useState("");
  const [previewHtml, setPreviewHtml] = useState("");
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const editorRef = useRef<HTMLDivElement>(null);
  const selectionRef = useRef<Range | null>(null);
  const selectedTemplate = templates.find((template) => String(template.id) === templateId);

  useEffect(() => {
    setPreviewOpen(false);
    setPreviewHtml("");
    setPreviewError("");
  }, [source, templateId, body]);

  function rememberSelection() {
    const selection = window.getSelection();
    if (
      selection?.rangeCount &&
      editorRef.current?.contains(selection.getRangeAt(0).commonAncestorContainer)
    ) {
      selectionRef.current = selection.getRangeAt(0).cloneRange();
    }
  }

  function restoreSelection() {
    const selection = window.getSelection();
    if (selectionRef.current && selection) {
      selection.removeAllRanges();
      selection.addRange(selectionRef.current);
    }
  }

  function runEditorCommand(command: string, value?: string) {
    const editor = editorRef.current;
    if (!editor) return;
    editor.focus();
    restoreSelection();
    document.execCommand(command, false, value);
    setBody(editor.innerHTML);
    rememberSelection();
  }

  function focusEditor() {
    const editor = editorRef.current;
    if (!editor) return;
    if (!editor.textContent?.trim() && !body) {
      for (const command of ["bold", "italic", "underline"]) {
        if (document.queryCommandState(command)) {
          document.execCommand(command, false);
        }
      }
      editor.innerHTML = "";
    }
    rememberSelection();
  }

  function insertPlaceholder(placeholder: string) {
    runEditorCommand("insertText", placeholder);
  }

  function insertWalletLink() {
    const editor = editorRef.current;
    if (!editor) return;
    editor.focus();
    restoreSelection();
    const selection = window.getSelection();
    const range = selection?.rangeCount ? selection.getRangeAt(0) : null;
    const anchor = document.createElement("a");
    anchor.setAttribute("href", "{{public_wallet}}");
    anchor.textContent = "Open public wallet";
    if (range && editor.contains(range.commonAncestorContainer)) {
      range.deleteContents();
      range.insertNode(anchor);
    } else {
      editor.appendChild(anchor);
    }
    const caretRange = document.createRange();
    caretRange.setStartAfter(anchor);
    caretRange.collapse(true);
    selection?.removeAllRanges();
    selection?.addRange(caretRange);
    selectionRef.current = caretRange.cloneRange();
    setBody(editor.innerHTML);
  }

  async function togglePreview() {
    if (previewOpen) {
      setPreviewOpen(false);
      return;
    }
    setPreviewError("");
    if (source === "basic") {
      setPreviewHtml(basicPreview(body));
      setPreviewOpen(true);
      return;
    }
    if (!templateId) return;
    setPreviewLoading(true);
    try {
      const result = await api<{ template: EmailTemplate }>(
        `/admin/events/${eventId}/email-templates/${templateId}`,
      );
      setPreviewHtml(sampleContent(result.template.rendered_html || ""));
      setPreviewOpen(true);
    } catch (failure) {
      setPreviewError(failure instanceof Error ? failure.message : "Preview could not be loaded.");
    } finally {
      setPreviewLoading(false);
    }
  }

  const canPreview = source === "template" ? Boolean(templateId) : Boolean(body.trim());

  return (
    <>
      <fieldset className="mt-4" disabled={disabled}>
        <legend className="text-sm font-semibold">Email content</legend>
        <div className="mt-2 grid grid-cols-2 gap-2">
          <label className={`button-secondary cursor-pointer ${source === "basic" ? "border-leaf-600 bg-leaf-50 text-leaf-800" : ""}`}>
            <input
              className="sr-only"
              type="radio"
              name="source"
              value="basic"
              checked={source === "basic"}
              onChange={() => setSource("basic")}
            />
            Basic message
          </label>
          <label className={`button-secondary cursor-pointer ${source === "template" ? "border-leaf-600 bg-leaf-50 text-leaf-800" : ""}`}>
            <input
              className="sr-only"
              type="radio"
              name="source"
              value="template"
              checked={source === "template"}
              onChange={() => setSource("template")}
            />
            Saved template
          </label>
        </div>
      </fieldset>

      {source === "template" ? (
        <Field label="Template">
          <select
            className="input"
            name="template_id"
            value={templateId}
            onChange={(event) => setTemplateId(event.target.value)}
            required
            disabled={disabled || loading}
          >
            <option value="">{loading ? "Loading templates…" : "Choose template"}</option>
            {templates.map((template) => (
              <option key={template.id} value={template.id}>{template.name}</option>
            ))}
          </select>
        </Field>
      ) : (
        <div className="mt-3">
          <span className="label">Message</span>
          <div className="rich-text-composer">
            <div className="rich-text-toolbar flex flex-wrap gap-1">
              <button className="button-secondary min-h-8 px-2" type="button" title="Bold" aria-label="Bold" onMouseDown={(event) => event.preventDefault()} onClick={() => runEditorCommand("bold")}>
                <Bold size={14} />
              </button>
              <button className="button-secondary min-h-8 px-2" type="button" title="Italic" aria-label="Italic" onMouseDown={(event) => event.preventDefault()} onClick={() => runEditorCommand("italic")}>
                <Italic size={14} />
              </button>
              <button className="button-secondary min-h-8 px-2" type="button" title="Underline" aria-label="Underline" onMouseDown={(event) => event.preventDefault()} onClick={() => runEditorCommand("underline")}>
                <Underline size={14} />
              </button>
              <label className="button-secondary min-h-8 cursor-pointer px-2 text-xs" title="Text color">
                <span>Color</span>
                <input
                  className="h-5 w-6 cursor-pointer border-0 bg-transparent p-0"
                  type="color"
                  defaultValue="#24342d"
                  aria-label="Text color"
                  onPointerDown={rememberSelection}
                  onChange={(event) => runEditorCommand("foreColor", event.target.value)}
                />
              </label>
              <button className="button-secondary min-h-8 px-2 text-xs" type="button" onClick={() => insertPlaceholder("{{participant_first_name}}")}>
                <UserRound size={14} /> First name
              </button>
              <button className="button-secondary min-h-8 px-2 text-xs" type="button" onClick={() => insertPlaceholder("{{participant_last_name}}")}>
                <UserRound size={14} /> Last name
              </button>
              <button className="button-secondary min-h-8 px-2 text-xs" type="button" onMouseDown={(event) => event.preventDefault()} onClick={insertWalletLink}>
                <Link2 size={14} /> Public wallet
              </button>
            </div>
            <div
              ref={editorRef}
              className="rich-text-editor"
              contentEditable={!disabled}
              role="textbox"
              aria-multiline="true"
              aria-required="true"
              data-placeholder="Write your message…"
              suppressContentEditableWarning
              onInput={(event) => setBody(event.currentTarget.innerHTML)}
              onKeyUp={rememberSelection}
              onMouseUp={rememberSelection}
              onFocus={focusEditor}
              onClick={(event) => {
                if ((event.target as HTMLElement).closest("a")) event.preventDefault();
              }}
            />
            <input type="hidden" name="body" value={body} />
          </div>
        </div>
      )}

      <Field label={source === "template" ? "Subject override (optional)" : "Subject"}>
        <input
          className="input"
          name="subject"
          maxLength={255}
          placeholder={source === "template" ? selectedTemplate?.subject : undefined}
          required={source === "basic"}
          disabled={disabled}
        />
      </Field>

      <button
        className="button-secondary mt-4"
        type="button"
        disabled={disabled || previewLoading || !canPreview}
        onClick={() => void togglePreview()}
      >
        <Eye size={16} />
        {previewLoading ? "Loading preview…" : previewOpen ? "Hide preview" : "Preview email"}
      </button>
      {previewError && <div className="alert-error mt-3 text-sm">{previewError}</div>}
      {previewOpen && (
        <iframe
          className="mt-3 min-h-96 w-full rounded border border-black/10 bg-white"
          sandbox=""
          title="Email preview"
          srcDoc={previewHtml}
        />
      )}
    </>
  );
}
