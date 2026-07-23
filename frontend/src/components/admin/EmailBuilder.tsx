"use client";

import { useMemo, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  Bold,
  Code2,
  Eye,
  FileJson,
  Heading,
  ImageIcon,
  Italic,
  Link,
  Minus,
  MousePointerClick,
  Plus,
  Save,
  Space,
  Trash2,
  Type,
  Underline,
} from "lucide-react";
import {
  Reader,
  renderToStaticMarkup,
  type TReaderDocument,
} from "@usewaypoint/email-builder";
import type {
  EmailAsset,
  EmailBlock,
  EmailDocument,
  EmailTemplate,
} from "./types";

type BlockType = "Heading" | "Text" | "Button" | "Image" | "Divider" | "Spacer" | "Html";
type View = "editor" | "preview" | "html" | "json";

const starterDocument: EmailDocument = {
  root: {
    type: "EmailLayout",
    data: {
      backdropColor: "#eef2ee",
      canvasColor: "#ffffff",
      textColor: "#24342d",
      fontFamily: "MODERN_SANS",
      childrenIds: ["welcome-heading", "welcome-text", "wallet-button"],
    },
  },
  "welcome-heading": {
    type: "Heading",
    data: {
      props: { level: "h2", text: "Hello, {{participant_first_name}}!" },
      style: {
        padding: { top: 32, right: 32, bottom: 12, left: 32 },
        fontWeight: "bold",
      },
    },
  },
  "welcome-text": {
    type: "Text",
    data: {
      props: { text: "Your event wallet is ready.", markdown: true },
      style: {
        padding: { top: 0, right: 32, bottom: 20, left: 32 },
        fontSize: 16,
      },
    },
  },
  "wallet-button": {
    type: "Button",
    data: {
      props: {
        text: "Open wallet",
        url: "{{wallet_link}}",
        buttonBackgroundColor: "#4fa800",
        buttonTextColor: "#ffffff",
        buttonStyle: "rounded",
        size: "large",
      },
      style: {
        padding: { top: 8, right: 32, bottom: 32, left: 32 },
        textAlign: "left",
      },
    },
  },
};

const placeholders = [
  ["First name", "{{participant_first_name}}"],
  ["Last name", "{{participant_last_name}}"],
  ["Full name", "{{participant_name}}"],
  ["Participant code", "{{participant_code}}"],
  ["Email", "{{participant_email}}"],
  ["Group", "{{participant_group}}"],
  ["Event name", "{{event_name}}"],
] as const;

function defaultBlock(type: BlockType): EmailBlock {
  const padding = { top: 16, right: 24, bottom: 16, left: 24 };
  if (type === "Heading")
    return { type, data: { props: { text: "New heading", level: "h2" }, style: { padding } } };
  if (type === "Text")
    return { type, data: { props: { text: "New text block", markdown: true }, style: { padding, fontSize: 16 } } };
  if (type === "Button")
    return {
      type,
      data: {
        props: {
          text: "Open",
          url: "https://example.com",
          buttonBackgroundColor: "#4fa800",
          buttonTextColor: "#ffffff",
          buttonStyle: "rounded",
          size: "medium",
        },
        style: { padding },
      },
    };
  if (type === "Image")
    return {
      type,
      data: {
        props: { url: "https://placehold.co/600x300/png", alt: "Image", contentAlignment: "middle" },
        style: { padding },
      },
    };
  if (type === "Divider")
    return { type, data: { props: { lineColor: "#d7ded9", lineHeight: 1 }, style: { padding } } };
  if (type === "Spacer") return { type, data: { props: { height: 32 } } };
  return {
    type,
    data: { props: { contents: "<p>Custom HTML content</p>" }, style: { padding } },
  };
}

function sampleHtml(source: string) {
  return source
    .replaceAll("{{participant_first_name}}", "Anna")
    .replaceAll("{{participant_last_name}}", "Bērziņa")
    .replaceAll("{{participant_name}}", "Anna Bērziņa")
    .replaceAll("{{participant_code}}", "P-1042")
    .replaceAll("{{participant_email}}", "anna@example.com")
    .replaceAll("{{participant_group}}", "Guests")
    .replaceAll("{{event_name}}", "Summer event")
    .replaceAll("{{wallet_link}}", "https://example.com/wallet");
}

export function EmailBuilder({
  template,
  assets,
  onSave,
  onClose,
}: {
  template?: EmailTemplate;
  assets: EmailAsset[];
  onSave: (value: {
    name: string;
    subject: string;
    document: EmailDocument;
    rendered_html: string;
    version?: number;
  }) => Promise<void>;
  onClose: () => void;
}) {
  const [document, setDocument] = useState<EmailDocument>(
    template?.document ?? starterDocument,
  );
  const [name, setName] = useState(template?.name ?? "");
  const [subject, setSubject] = useState(template?.subject ?? "");
  const [selectedId, setSelectedId] = useState<string | null>(
    template ? null : "welcome-heading",
  );
  const [view, setView] = useState<View>("editor");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const nextBlockId = useRef(0);
  const textEditorRef = useRef<HTMLTextAreaElement>(null);
  const childIds = (document.root.data.childrenIds as string[] | undefined) ?? [];
  const selected = selectedId ? document[selectedId] : undefined;
  const renderedHtml = useMemo(
    () => renderToStaticMarkup(document as TReaderDocument, { rootBlockId: "root" }),
    [document],
  );

  function changeRoot(childrenIds: string[]) {
    setDocument({
      ...document,
      root: {
        ...document.root,
        data: { ...document.root.data, childrenIds },
      },
    });
  }

  function addBlock(type: BlockType) {
    nextBlockId.current += 1;
    const id = `new-block-${nextBlockId.current}`;
    setDocument({
      ...document,
      [id]: defaultBlock(type),
      root: {
        ...document.root,
        data: { ...document.root.data, childrenIds: [...childIds, id] },
      },
    });
    setSelectedId(id);
  }

  function moveBlock(id: string, direction: -1 | 1) {
    const index = childIds.indexOf(id);
    const target = index + direction;
    if (target < 0 || target >= childIds.length) return;
    const next = [...childIds];
    [next[index], next[target]] = [next[target], next[index]];
    changeRoot(next);
  }

  function removeBlock(id: string) {
    const next = { ...document };
    delete next[id];
    next.root = {
      ...next.root,
      data: {
        ...next.root.data,
        childrenIds: childIds.filter((childId) => childId !== id),
      },
    };
    setDocument(next);
    setSelectedId(null);
  }

  function updateSelected(data: EmailBlock["data"]) {
    if (!selectedId || !selected) return;
    setDocument({ ...document, [selectedId]: { ...selected, data } });
  }

  function setProp(key: string, value: unknown) {
    if (!selected) return;
    updateSelected({
      ...selected.data,
      props: { ...(selected.data.props ?? {}), [key]: value },
    });
  }

  function setStyle(key: string, value: unknown) {
    if (!selected) return;
    updateSelected({
      ...selected.data,
      style: { ...(selected.data.style ?? {}), [key]: value },
    });
  }

  function wrapSelectedText(before: string, after: string = before) {
    const editor = textEditorRef.current;
    if (!editor || !selected) return;
    const value = String(selected.data.props?.text ?? "");
    const start = editor.selectionStart;
    const end = editor.selectionEnd;
    const selection = value.slice(start, end) || "text";
    setProp(
      "text",
      `${value.slice(0, start)}${before}${selection}${after}${value.slice(end)}`,
    );
    requestAnimationFrame(() => {
      editor.focus();
      editor.setSelectionRange(
        start + before.length,
        start + before.length + selection.length,
      );
    });
  }

  function insertPlaceholder(value: string) {
    if (!selected) return;
    const props = selected.data.props ?? {};
    setProp("text", `${String(props.text ?? "")}${value}`);
  }

  async function save() {
    setSaving(true);
    setError("");
    try {
      await onSave({
        name,
        subject,
        document,
        rendered_html: renderedHtml,
        version: template?.version,
      });
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Template could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  const palette = [
    ["Heading", "Heading", Heading],
    ["Text", "Text", Type],
    ["Button", "Button", MousePointerClick],
    ["Image", "Image", ImageIcon],
    ["Divider", "Divider", Minus],
    ["Spacer", "Spacer", Space],
    ["Html", "HTML", Code2],
  ] as const;

  return (
    <div className="card overflow-hidden">
      <div className="flex flex-wrap items-end gap-3 border-b border-black/10 p-4">
        <label className="min-w-48 flex-1">
          <span className="label">Template name</span>
          <input className="input" value={name} onChange={(event) => setName(event.target.value)} />
        </label>
        <label className="min-w-64 flex-[2]">
          <span className="label">Default subject</span>
          <input className="input" value={subject} onChange={(event) => setSubject(event.target.value)} />
        </label>
        <button className="button" disabled={saving || !name.trim() || !subject.trim()} onClick={() => void save()}>
          <Save size={16} /> {saving ? "Saving…" : "Save"}
        </button>
        <button className="button-secondary" onClick={onClose}>Close</button>
      </div>
      {error && <div className="alert-error m-4 text-sm">{error}</div>}

      <div className="grid min-h-[680px] xl:grid-cols-[190px_minmax(0,1fr)_280px]">
        <aside className="border-r border-black/10 p-3">
          <p className="label">Blocks</p>
          <div className="grid gap-1">
            {palette.map(([type, label, Icon]) => (
              <button key={type} className="button-secondary justify-between px-3" onClick={() => addBlock(type)}>
                <span className="flex items-center gap-2"><Icon size={16} />{label}</span><Plus size={14} />
              </button>
            ))}
          </div>
          <p className="label mt-5">Personalization</p>
          <div className="grid gap-1">
            {placeholders.map(([label, value]) => (
              <button
                key={value}
                className="rounded px-2 py-1.5 text-left text-sm hover:bg-black/5 disabled:opacity-40"
                disabled={!selected || !["Heading", "Text", "Button"].includes(selected.type)}
                onClick={() => insertPlaceholder(value)}
              >
                {label}
              </button>
            ))}
            <button
              className="rounded px-2 py-1.5 text-left text-sm hover:bg-black/5 disabled:opacity-40"
              disabled={!selected || !["Button", "Image"].includes(selected.type)}
              onClick={() => setProp(selected?.type === "Image" ? "linkHref" : "url", "{{wallet_link}}")}
            >
              <Link className="mr-2 inline" size={14} />Wallet link
            </button>
          </div>
        </aside>

        <main className="min-w-0 bg-[#eef2ee]">
          <div className="flex gap-1 overflow-auto border-b border-black/10 bg-white p-2">
            {([
              ["editor", "Editor", Type],
              ["preview", "Preview", Eye],
              ["html", "HTML", Code2],
              ["json", "JSON", FileJson],
            ] as const).map(([key, label, Icon]) => (
              <button
                key={key}
                className={view === key ? "button min-h-9 px-3" : "button-secondary min-h-9 px-3"}
                onClick={() => setView(key)}
              >
                <Icon size={15} />{label}
              </button>
            ))}
          </div>
          <div className="p-5">
            {view === "editor" && (
              <div className="mx-auto max-w-[680px] bg-white p-2 shadow-lg">
                {childIds.map((id, index) => (
                  <div
                    key={id}
                    className={`group relative cursor-pointer border-2 ${selectedId === id ? "border-leaf-500" : "border-transparent hover:border-black/15"}`}
                    onClick={() => setSelectedId(id)}
                  >
                    <Reader
                      document={{
                        root: {
                          ...document.root,
                          data: { ...document.root.data, childrenIds: [id] },
                        },
                        [id]: document[id],
                      } as TReaderDocument}
                      rootBlockId="root"
                    />
                    <div className="absolute right-1 top-1 hidden gap-1 group-hover:flex">
                      <button className="button-secondary min-h-8 bg-white p-1" disabled={index === 0} onClick={(event) => { event.stopPropagation(); moveBlock(id, -1); }}><ArrowUp size={14} /></button>
                      <button className="button-secondary min-h-8 bg-white p-1" disabled={index === childIds.length - 1} onClick={(event) => { event.stopPropagation(); moveBlock(id, 1); }}><ArrowDown size={14} /></button>
                      <button className="button-secondary min-h-8 bg-white p-1 text-red-700" onClick={(event) => { event.stopPropagation(); removeBlock(id); }}><Trash2 size={14} /></button>
                    </div>
                  </div>
                ))}
              </div>
            )}
            {view === "preview" && <iframe className="mx-auto block min-h-[600px] w-full max-w-[680px] bg-white shadow-lg" sandbox="" title="Email preview" srcDoc={sampleHtml(renderedHtml)} />}
            {view === "html" && <pre className="max-h-[620px] overflow-auto whitespace-pre-wrap rounded bg-slate-950 p-4 text-xs text-slate-100">{renderedHtml}</pre>}
            {view === "json" && <pre className="max-h-[620px] overflow-auto whitespace-pre-wrap rounded bg-slate-950 p-4 text-xs text-slate-100">{JSON.stringify(document, null, 2)}</pre>}
          </div>
        </main>

        <aside className="border-l border-black/10 p-4">
          <h4 className="font-semibold">{selected ? selected.type : "Email layout"}</h4>
          {!selected && <p className="mt-2 text-sm text-black/50">Select a block to edit its content and styling.</p>}
          {selected && (
            <div className="mt-4 grid gap-3">
              {["Heading", "Text", "Button"].includes(selected.type) && (
                <label>
                  <span className="label">Text</span>
                  {selected.type === "Text" && (
                    <div className="mb-2 flex flex-wrap gap-1">
                      <button className="button-secondary min-h-8 px-2" type="button" title="Bold selected text" aria-label="Bold selected text" onClick={() => wrapSelectedText("**")}><Bold size={14} /></button>
                      <button className="button-secondary min-h-8 px-2" type="button" title="Italic selected text" aria-label="Italic selected text" onClick={() => wrapSelectedText("*")}><Italic size={14} /></button>
                      <button className="button-secondary min-h-8 px-2" type="button" title="Underline selected text" aria-label="Underline selected text" onClick={() => wrapSelectedText("<u>", "</u>")}><Underline size={14} /></button>
                      <label className="button-secondary min-h-8 cursor-pointer px-2 text-xs" title="Selected text color">
                        Color
                        <input
                          className="h-5 w-6 cursor-pointer border-0 bg-transparent p-0"
                          type="color"
                          defaultValue="#24342d"
                          aria-label="Selected text color"
                          onChange={(event) => wrapSelectedText(`<span style="color:${event.target.value}">`, "</span>")}
                        />
                      </label>
                    </div>
                  )}
                  <textarea ref={selected.type === "Text" ? textEditorRef : undefined} className="input min-h-28" value={String(selected.data.props?.text ?? "")} onChange={(event) => setProp("text", event.target.value)} />
                </label>
              )}
              {["Heading", "Text"].includes(selected.type) && (
                <div className="grid grid-cols-2 gap-2">
                  <button
                    className={selected.data.style?.fontWeight === "bold" ? "button min-h-9 px-3" : "button-secondary min-h-9 px-3"}
                    type="button"
                    onClick={() => setStyle("fontWeight", selected.data.style?.fontWeight === "bold" ? "normal" : "bold")}
                  >
                    <Bold size={14} /> Block bold
                  </button>
                  <label className="button-secondary min-h-9 cursor-pointer px-3 text-xs">
                    Block color
                    <input
                      className="h-5 w-6 cursor-pointer border-0 bg-transparent p-0"
                      type="color"
                      value={String(selected.data.style?.color ?? "#24342d")}
                      onChange={(event) => setStyle("color", event.target.value)}
                    />
                  </label>
                </div>
              )}
              {selected.type === "Button" && (
                <>
                  <label><span className="label">URL</span><input className="input" value={String(selected.data.props?.url ?? "")} onChange={(event) => setProp("url", event.target.value)} /></label>
                  <label><span className="label">Button color</span><input className="input" type="color" value={String(selected.data.props?.buttonBackgroundColor ?? "#4fa800")} onChange={(event) => setProp("buttonBackgroundColor", event.target.value)} /></label>
                </>
              )}
              {selected.type === "Image" && (
                <>
                  <label>
                    <span className="label">Event image</span>
                    <select className="input" value={assets.some((asset) => asset.url === selected.data.props?.url) ? String(selected.data.props?.url) : ""} onChange={(event) => setProp("url", event.target.value)}>
                      <option value="">Choose an uploaded image</option>
                      {assets.map((asset) => <option key={asset.id} value={asset.url}>{asset.original_name} ({asset.width} × {asset.height})</option>)}
                    </select>
                  </label>
                  <label><span className="label">Image URL</span><input className="input" value={String(selected.data.props?.url ?? "")} onChange={(event) => setProp("url", event.target.value)} /></label>
                  <label><span className="label">Alternative text</span><input className="input" value={String(selected.data.props?.alt ?? "")} onChange={(event) => setProp("alt", event.target.value)} /></label>
                  <label><span className="label">Click URL</span><input className="input" value={String(selected.data.props?.linkHref ?? "")} onChange={(event) => setProp("linkHref", event.target.value)} /></label>
                </>
              )}
              {selected.type === "Html" && <label><span className="label">HTML</span><textarea className="input min-h-48 font-mono text-xs" value={String(selected.data.props?.contents ?? "")} onChange={(event) => setProp("contents", event.target.value)} /></label>}
              {selected.type === "Spacer" && <label><span className="label">Height</span><input className="input" type="number" min="1" max="500" value={Number(selected.data.props?.height ?? 32)} onChange={(event) => setProp("height", Number(event.target.value))} /></label>}
              {selected.type === "Divider" && <label><span className="label">Line color</span><input className="input" type="color" value={String(selected.data.props?.lineColor ?? "#d7ded9")} onChange={(event) => setProp("lineColor", event.target.value)} /></label>}
            </div>
          )}
          <p className="mt-8 text-xs text-black/40">Built with EmailBuilder.js (MIT).</p>
        </aside>
      </div>
    </div>
  );
}
