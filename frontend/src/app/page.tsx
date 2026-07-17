import Link from "next/link";
import { ArrowRight, QrCode, ShieldCheck, Tickets } from "lucide-react";
import { PublicShell } from "@/components/Shell";

export default function Home() {
  return <PublicShell><section className="mx-auto grid max-w-6xl gap-12 px-5 pb-20 pt-12 lg:grid-cols-[1.2fr_.8fr] lg:items-center"><div><span className="badge bg-leaf-50 text-leaf-700">Wallets, payments and coupons</span><h1 className="mt-6 max-w-3xl font-[var(--font-display)] text-5xl font-extrabold leading-tight md:text-7xl">Run event spending without the spreadsheet chaos.</h1><p className="mt-6 max-w-2xl text-lg text-black/60">Create participant wallets, issue coupons, accept QR payments and keep a complete audit trail from one independent service.</p><div className="mt-8 flex flex-wrap gap-3"><Link className="button" href="/admin">Administrator <ArrowRight size={18}/></Link><Link className="button-secondary" href="/wallet">Vendor wallet</Link></div></div><div className="card grid gap-4 p-5 sm:grid-cols-2 lg:grid-cols-1"><Feature icon={<QrCode/>} title="Replay-safe QR" text="Short-lived payment grants are consumed atomically."/><Feature icon={<Tickets/>} title="Flexible coupons" text="Universal or vendor-specific, with an immutable audit trail."/><Feature icon={<ShieldCheck/>} title="Scoped by event" text="Concurrent live events never share participants or vendors."/></div></section></PublicShell>;
}

function Feature({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) { return <article className="rounded-xl bg-canvas p-5"><div className="text-leaf-600">{icon}</div><h2 className="mt-3 font-bold">{title}</h2><p className="mt-1 text-sm text-black/55">{text}</p></article>; }

