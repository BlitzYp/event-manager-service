"use client";

import { useMemo, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  Code2,
  Eye,
  FileJson,
  Heading,
  ImageIcon,
  Link,
  Minus,
  MousePointerClick,
  Plus,
  Save,
  Space,
  Trash2,
  Type,
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

import { BlockInspector } from "./email-builder/BlockInspector";
import { defaultBlock, placeholders, sampleHtml, starterDocument, type BlockType } from "./email-builder/document";

type View = "editor" | "preview" | "html" | "json";

/** Compose a block document, preview its HTML, and save the current template version. */
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
  // Saved template fields, editable block tree, selection, and preview state.
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
  /** Render the current block document to the HTML payload saved with the template. */
  const renderedHtml = useMemo(
    () => renderToStaticMarkup(document as TReaderDocument, { rootBlockId: "root" }),
    [document],
  );

  /** Replace the ordered top-level block IDs while retaining the current email layout settings. */
  function changeRoot(childrenIds: string[]) {
    setDocument({
      ...document,
      root: {
        ...document.root,
        data: { ...document.root.data, childrenIds },
      },
    });
  }

  /** Append a fresh block to the document and select it for editing. */
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

  /** Move one block up or down without moving it outside the document bounds. */
  function moveBlock(id: string, direction: -1 | 1) {
    const index = childIds.indexOf(id);
    const target = index + direction;
    if (target < 0 || target >= childIds.length) return;
    const next = [...childIds];
    [next[index], next[target]] = [next[target], next[index]];
    changeRoot(next);
  }

  /** Remove a block and its layout reference, then clear the inspector selection. */
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

  /** Replace only the selected block data while preserving all other document blocks. */
  function updateSelected(data: EmailBlock["data"]) {
    if (!selectedId || !selected) return;
    setDocument({ ...document, [selectedId]: { ...selected, data } });
  }

  /** Merge a content property into the selected block without discarding its other properties. */
  function setProp(key: string, value: unknown) {
    if (!selected) return;
    updateSelected({
      ...selected.data,
      props: { ...(selected.data.props ?? {}), [key]: value },
    });
  }

  /** Merge a style property into the selected block without discarding its other styles. */
  function setStyle(key: string, value: unknown) {
    if (!selected) return;
    updateSelected({
      ...selected.data,
      style: { ...(selected.data.style ?? {}), [key]: value },
    });
  }

  /** Wrap the textarea selection in formatting markers and restore focus to the edited text. */
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

  /** Append a supported personalization token to the selected block text. */
  function insertPlaceholder(value: string) {
    if (!selected) return;
    const props = selected.data.props ?? {};
    setProp("text", `${String(props.text ?? "")}${value}`);
  }

  /** Pass the current name, subject, document, rendered HTML, and version to the save callback. */
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

  // Blocks offered in the editor sidebar, paired with labels and icons.
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

        <BlockInspector
          selected={selected}
          assets={assets}
          textEditorRef={textEditorRef}
          setProp={setProp}
          setStyle={setStyle}
          wrapSelectedText={wrapSelectedText}
        />
      </div>
    </div>
  );
}
