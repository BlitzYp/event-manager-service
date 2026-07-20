"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import QRCode from "qrcode";
import { Check, Clock3, RefreshCw, Ticket, WalletCards, X } from "lucide-react";
import { PublicShell } from "@/components/Shell";
import { api, money } from "@/lib/api";

type State = {
  event: { name: string; mode: string; currency: string };
  participant: { code: string; name: string; group?: string };
  wallet: {
    id: number;
    enabled: boolean;
    balance_minor: number;
    reserved_minor: number;
  };
  pending: Transaction[];
  transactions: Transaction[];
  coupons: { id: number; name: string; status: string; code: string; qr_token?: string }[];
};
type Transaction = {
  id: number;
  reference: string;
  type: string;
  status: string;
  amount_minor: number;
  vendor_name?: string;
  created_at: string;
  expires_at?: string;
};

export default function ParticipantWallet() {
  const params = useParams<{ token: string }>();
  const token = params.token;
  const [state, setState] = useState<State>();
  const [error, setError] = useState("");
  const [qr, setQr] = useState("");
  const [ttl, setTtl] = useState(0);
  const load = useCallback(async () => {
    try {
      setState(
        await api<State>(`/participant/wallet/${encodeURIComponent(token)}`),
      );
      setError("");
    } catch (x) {
      setError(x instanceof Error ? x.message : "Wallet is unavailable.");
    }
  }, [token]);
  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    if (ttl <= 0) return;
    const id = setInterval(() => setTtl((v) => Math.max(0, v - 1)), 1000);
    return () => clearInterval(id);
  }, [ttl]);
  async function createQr() {
    const r = await api<{ token: string; ttl_seconds: number }>(
      `/participant/wallet/${encodeURIComponent(token)}/payment-qr`,
      { method: "POST" },
    );
    setQr(
      await QRCode.toDataURL(r.token, {
        width: 360,
        margin: 2,
        color: { dark: "#15201c", light: "#ffffff" },
      }),
    );
    setTtl(r.ttl_seconds);
  }
  async function decide(id: number, decision: "approved" | "rejected") {
    await api(
      `/participant/wallet/${encodeURIComponent(token)}/payments/${id}/decision`,
      { method: "POST", body: JSON.stringify({ decision }) },
    );
    await load();
  }
  if (error)
    return (
      <PublicShell>
        <section className="mx-auto max-w-xl px-5 py-20">
          <div className="card p-8 text-center">
            <X className="mx-auto text-red-600" size={44} />
            <h1 className="mt-4 text-2xl font-bold">Wallet unavailable</h1>
            <p className="mt-2 text-black/50">{error}</p>
          </div>
        </section>
      </PublicShell>
    );
  if (!state)
    return (
      <div className="grid min-h-screen place-items-center">
        <RefreshCw className="animate-spin text-leaf-600" />
      </div>
    );
  const available = state.wallet.balance_minor - state.wallet.reserved_minor;
  return (
    <PublicShell>
      <section className="mx-auto max-w-[680px] px-5 pb-16 pt-8">
        <div className="mb-6">
          <p className="text-xs font-bold uppercase tracking-wide text-black/70">
            {state.event.name}
          </p>
          <h1 className="mt-1 text-3xl font-semibold">
            My virtual wallet
          </h1>
          <p className="text-black/45">
            {state.participant.code} ·{" "}
            {state.participant.group || "Participant"}
          </p>
        </div>
        {!state.wallet.enabled && (
          <div className="alert-warning mb-5">
            This wallet is currently disabled.
          </div>
        )}
        {state.event.mode !== "coupons" && (
          <section className="wallet-balance-card">
            <div className="flex items-center gap-3">
              <span className="wallet-icon"><WalletCards /></span>
              <div>
                <small className="text-white/80">Available balance</small>
                <p className="text-5xl font-bold">{money(available, state.event.currency)}</p>
                {state.wallet.reserved_minor > 0 && (
                  <small className="text-white/75">
                    Reserved: {money(state.wallet.reserved_minor, state.event.currency)}
                  </small>
                )}
              </div>
            </div>
          </section>
        )}
        {state.event.mode !== "coupons" && state.wallet.enabled && (
          <section className="card mt-5 p-6 text-center">
            <h2 className="text-xl font-bold">Payment QR</h2>
            <p className="mt-1 text-sm text-black/50">
              Show this short-lived code to the vendor.
            </p>
            {qr && ttl > 0 ? (
              <>
                <div className="wallet-qr-frame mt-5">
                  <img src={qr} alt="One-time payment QR code" />
                </div>
                <p className="mt-3 flex items-center justify-center gap-2 text-sm font-semibold text-leaf-700">
                  <Clock3 size={16} /> Valid for {ttl}s
                </p>
              </>
            ) : (
              <button className="button mt-6" onClick={() => void createQr()}>
                <RefreshCw size={18} /> Generate payment QR
              </button>
            )}
          </section>
        )}
        {state.pending.map((p) => (
          <section className="card mt-5 border border-amber-300 p-5" key={p.id}>
            <div className="flex items-start justify-between gap-4">
              <div className="flex gap-3">
                <span className="wallet-pending-icon"><Clock3 size={20} /></span>
                <div>
                <span className="badge bg-amber-50 text-amber-800">
                  Approval needed
                </span>
                <h2 className="mt-2 text-xl font-bold">{p.vendor_name}</h2>
                <p className="text-sm text-black/45">{p.reference}</p>
                </div>
              </div>
              <strong className="text-2xl">
                {money(p.amount_minor, state.event.currency)}
              </strong>
            </div>
            <div className="mt-5 grid grid-cols-2 gap-3">
              <button
                className="button-secondary"
                onClick={() => void decide(p.id, "rejected")}
              >
                <X size={18} /> Reject
              </button>
              <button
                className="button"
                onClick={() => void decide(p.id, "approved")}
              >
                <Check size={18} /> Approve
              </button>
            </div>
          </section>
        ))}
        {state.event.mode !== "money" && (
          <section className="card mt-5 p-6">
            <div className="flex items-center gap-2">
              <Ticket className="text-leaf-600" />
              <h2 className="text-xl font-bold">Coupons</h2>
            </div>
            <div className="mt-4 grid gap-3">
              {state.coupons.map((c) => (
                <CouponCard key={c.id} coupon={c} />
              ))}
            </div>
          </section>
        )}
        <section className="card mt-5 p-6">
          <h2 className="text-xl font-bold">Recent activity</h2>
          <div className="mt-4 divide-y divide-black/5">
            {state.transactions.map((t) => (
              <div
                className="wallet-transaction"
                key={t.id}
              >
                <span className="wallet-transaction-icon"><WalletCards size={19} /></span>
                <div>
                  <strong>{t.vendor_name || "Wallet administrator"}</strong>
                  <p className="text-xs text-black/45">
                    {new Date(t.created_at).toLocaleString()} · {t.status}
                  </p>
                </div>
                <strong
                  className={`ml-auto ${
                    t.type === "vendor_debit" ? "text-red-600" : "text-leaf-700"
                  }`}
                >
                  {t.type === "vendor_debit" ? "-" : "+"}
                  {money(t.amount_minor, state.event.currency)}
                </strong>
              </div>
            ))}
          </div>
        </section>
      </section>
    </PublicShell>
  );
}

function CouponCard({ coupon }: { coupon: State["coupons"][number] }) {
  const [open, setOpen] = useState(false);
  const [src, setSrc] = useState("");
  async function show() {
    if (coupon.qr_token) {
      setSrc(
        await QRCode.toDataURL(coupon.qr_token, { width: 320, margin: 2 }),
      );
      setOpen(true);
    }
  }
  return (
    <article className="border-b border-black/10 last:border-0">
      <div className="wallet-transaction">
        <span className="wallet-transaction-icon"><Ticket size={19} /></span>
        <div className="flex flex-1 items-center justify-between gap-3">
          <div>
            <strong>{coupon.name}</strong>
            <p className="text-xs uppercase text-black/40">{coupon.status}</p>
            <p className="mt-1 font-mono text-xs font-semibold">{coupon.code}</p>
          </div>
          {coupon.status === "available" && (
            <button
              className="button min-h-9 px-3 py-1 text-sm"
              onClick={() => void show()}
            >
              Show QR
            </button>
          )}
        </div>
      </div>
      {open && (
        <div className="pb-5 text-center">
          <div className="wallet-qr-frame">
            <img src={src} alt={`${coupon.name} coupon QR`} />
          </div>
          <button
            className="mt-2 text-sm font-semibold text-black/45"
            onClick={() => setOpen(false)}
          >
            Hide
          </button>
        </div>
      )}
    </article>
  );
}
