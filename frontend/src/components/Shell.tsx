import Link from "next/link";
import { CalendarRange } from "lucide-react";

export function Brand() {
  return (
    <Link href="/" className="inline-flex items-center gap-3 font-bold">
      <span className="grid h-10 w-10 place-items-center rounded-lg bg-white/15 text-white">
        <CalendarRange size={22} />
      </span>
      <span>Event Manager</span>
    </Link>
  );
}

export function PublicShell({ children }: { children: React.ReactNode }) {
  return (
    <main className="min-h-screen bg-canvas">
      <header className="bg-gradient-to-br from-[#397c22] to-leaf-600 text-white shadow-sm">
        <div className="mx-auto max-w-6xl px-5 py-3">
          <Brand />
        </div>
      </header>
      {children}
    </main>
  );
}
