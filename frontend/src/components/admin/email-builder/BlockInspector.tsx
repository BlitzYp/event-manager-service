"use client";

import type { RefObject } from "react";
import { Bold, Italic, Underline } from "lucide-react";
import type { EmailAsset, EmailBlock } from "../types";

type BlockInspectorProps = {
  selected?: EmailBlock;
  assets: EmailAsset[];
  textEditorRef: RefObject<HTMLTextAreaElement | null>;
  setProp: (key: string, value: unknown) => void;
  setStyle: (key: string, value: unknown) => void;
  wrapSelectedText: (before: string, after?: string) => void;
};

/** Edit the selected block's content and style through the parent document handlers. */
export function BlockInspector({
  selected, assets, textEditorRef, setProp, setStyle, wrapSelectedText,
}: BlockInspectorProps) {
  return (
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
  );
}
