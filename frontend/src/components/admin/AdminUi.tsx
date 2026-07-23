import type { ReactNode } from "react";

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="mt-3 block flex-1">
      <span className="label">{label}</span>
      {children}
    </label>
  );
}

export function Empty({ text }: { text: string }) {
  return (
    <div className="col-span-full rounded-xl border border-dashed border-black/15 p-8 text-center text-sm text-black/45">
      {text}
    </div>
  );
}
