import Link from "next/link";
import { CalendarRange } from "lucide-react";

export function Brand() {
  return <Link href="/" className="inline-flex items-center gap-3 font-bold"><span className="grid h-10 w-10 place-items-center rounded-xl bg-leaf-600 text-white"><CalendarRange size={22}/></span><span>Event Manager</span></Link>;
}

export function PublicShell({ children }: { children: React.ReactNode }) {
  return <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(47,143,91,.16),_transparent_36%)]"><header className="mx-auto max-w-6xl px-5 py-6"><Brand /></header>{children}</main>;
}

