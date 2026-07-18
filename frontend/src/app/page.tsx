import Link from "next/link";
import { ArrowRight, QrCode, Settings, ShieldCheck, Store, Tickets } from "lucide-react";
import { PublicShell } from "@/components/Shell";

export default function Home() {
  return (
    <PublicShell>
      <section className="mx-auto max-w-5xl px-5 py-12 md:py-16">
        <div className="mb-8">
          <p className="text-sm font-bold uppercase tracking-wide text-leaf-700">Event operations</p>
          <h1 className="mt-1 text-4xl font-semibold">Event wallet manager</h1>
          <p className="mt-2 max-w-2xl text-black/55">
            Manage participant wallets, vendor payments, coupons, and complete audit history.
          </p>
        </div>

        <div className="grid gap-5 md:grid-cols-2">
          <PortalCard
            href="/admin"
            icon={<Settings size={28} />}
            title="Administration"
            text="Configure events, participants, vendors, coupons, automation, and ledgers."
          />
          <PortalCard
            href="/wallet"
            icon={<Store size={28} />}
            title="Vendor portal"
            text="Scan participant QR codes, accept payments, and redeem event coupons."
          />
        </div>

        <div className="card mt-8 grid gap-0 p-5 sm:grid-cols-3">
          <Feature icon={<QrCode />} title="Secure QR" text="Short-lived, replay-safe grants" />
          <Feature icon={<Tickets />} title="Coupons" text="Universal or vendor-specific" />
          <Feature icon={<ShieldCheck />} title="Event scoped" text="Independent balances and access" />
        </div>
      </section>
    </PublicShell>
  );
}

function PortalCard({ href, icon, title, text }: { href: string; icon: React.ReactNode; title: string; text: string }) {
  return (
    <Link href={href} className="card group flex items-center gap-4 p-6 transition hover:-translate-y-0.5 hover:shadow-lg">
      <span className="wallet-icon h-14 w-14 text-leaf-600">{icon}</span>
      <span className="flex-1">
        <strong className="block text-xl">{title}</strong>
        <span className="mt-1 block text-sm text-black/55">{text}</span>
      </span>
      <ArrowRight className="text-black/30 transition group-hover:translate-x-1 group-hover:text-leaf-600" />
    </Link>
  );
}

function Feature({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) {
  return (
    <div className="flex gap-3 border-b border-black/5 p-4 last:border-0 sm:border-b-0 sm:border-r sm:last:border-r-0">
      <span className="text-leaf-600">{icon}</span>
      <div><strong>{title}</strong><p className="text-sm text-black/50">{text}</p></div>
    </div>
  );
}
