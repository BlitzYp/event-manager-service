"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { BrowserQRCodeReader, IScannerControls } from "@zxing/browser";
import {
  ArrowLeft,
  Camera,
  CheckCircle2,
  LogOut,
  Search,
  Store,
  Ticket,
  X,
} from "lucide-react";
import { PublicShell } from "@/components/Shell";
import { ApiFailure, api, money } from "@/lib/api";

type Vendor = {
  id: number;
  name: string;
  event_id: number;
  event_name: string;
};
type Wallet = {
  id: number;
  participant_code: string;
  participant_name: string;
  group?: string;
  balance_minor: number;
  reserved_minor: number;
  currency: string;
  coupons: Coupon[];
};
type Coupon = {
  token?: string | null;
  code: string;
  name: string;
  status: string;
  participant_name: string;
};

export default function VendorWalletPage() {
  const [vendor, setVendor] = useState<Vendor | null>(null);
  const [csrf, setCsrf] = useState("");
  const [error, setError] = useState("");
  const bootstrap = useCallback(async () => {
    try {
      const me = await api<{ vendor: Vendor }>("/vendor/me");
      const token = await api<{ csrf_token: string }>("/vendor/csrf", {
        method: "POST",
      });
      setVendor(me.vendor);
      setCsrf(token.csrf_token);
    } catch {
      setVendor(null);
    }
  }, []);
  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);
  async function login(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    const f = new FormData(e.currentTarget);
    try {
      const result = await api<{ vendor: Vendor; csrf_token: string }>(
        "/vendor/login",
        {
          method: "POST",
          body: JSON.stringify({
            event_code: f.get("event_code"),
            pin: f.get("pin"),
          }),
        },
      );
      setVendor(result.vendor);
      setCsrf(result.csrf_token);
    } catch (x) {
      setError(x instanceof ApiFailure ? x.message : "Sign in failed.");
    }
  }
  if (!vendor)
    return (
      <PublicShell>
        <section className="mx-auto max-w-md px-5 py-12 md:py-16">
          <form onSubmit={login} className="card p-7 text-center md:p-8">
            <span className="wallet-pending-icon mx-auto mb-3">
              <Store />
            </span>
            <h1 className="text-3xl font-semibold">
              Vendor sign in
            </h1>
            <p className="mt-2 text-sm text-black/55">
              Enter the event code and PIN supplied by the event administrator.
            </p>
            {error && (
              <p className="alert-error mt-5 text-left text-sm">
                {error}
              </p>
            )}
            <label className="label mt-6 text-left">Event code</label>
            <input
              className="input"
              name="event_code"
              autoCapitalize="none"
              required
            />
            <label className="label mt-4 text-left">Six-digit PIN</label>
            <input
              className="input text-center text-2xl tracking-[.35em]"
              name="pin"
              type="password"
              inputMode="numeric"
              pattern="\d{6}"
              maxLength={6}
              required
            />
            <button className="button mt-6 w-full">Open vendor wallet</button>
          </form>
        </section>
      </PublicShell>
    );
  return (
    <VendorConsole
      vendor={vendor}
      csrf={csrf}
      onSessionExpired={() => setVendor(null)}
      onLogout={async () => {
        await api("/vendor/logout", { method: "POST" }, csrf);
        setVendor(null);
      }}
    />
  );
}

function VendorConsole({
  vendor,
  csrf,
  onLogout,
  onSessionExpired,
}: {
  vendor: Vendor;
  csrf: string;
  onLogout: () => Promise<void>;
  onSessionExpired: () => void;
}) {
  const [step, setStep] = useState<
    "start" | "scan" | "wallet" | "coupon" | "result"
  >("start");
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [paymentToken, setPaymentToken] = useState<string | null>(null);
  const [coupon, setCoupon] = useState<Coupon | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const video = useRef<HTMLVideoElement>(null);
  const controls = useRef<IScannerControls | undefined>(undefined);
  useEffect(() => {
    const interval = window.setInterval(async () => {
      try {
        await api("/vendor/me");
      } catch {
        controls.current?.stop();
        onSessionExpired();
      }
    }, 10_000);
    return () => window.clearInterval(interval);
  }, [onSessionExpired]);
  const lookup = useCallback(async (value: string, isCode = false) => {
    setError("");
    try {
      const query = isCode
        ? `participant_code=${encodeURIComponent(value)}`
        : `qr_token=${encodeURIComponent(value)}`;
      const result = await api<{
        kind: "wallet" | "coupon";
        wallet?: Wallet;
        coupon?: Coupon;
      }>(`/vendor/lookup?${query}`);
      if (result.kind === "coupon" && result.coupon) {
        setCoupon(result.coupon);
        setStep("coupon");
      } else if (result.wallet) {
        setWallet(result.wallet);
        setPaymentToken(isCode ? null : value);
        setStep("wallet");
      }
    } catch (x) {
      if (x instanceof ApiFailure && x.status === 401) {
        onSessionExpired();
        return;
      }
      setError(x instanceof Error ? x.message : "Nothing was found.");
      setStep("start");
    }
  }, [onSessionExpired]);
  const lookupCouponCode = useCallback(async (value: string) => {
    setError("");
    try {
      const result = await api<{ kind: "coupon"; coupon: Coupon }>(
        `/vendor/lookup?coupon_code=${encodeURIComponent(value)}`,
      );
      setCoupon(result.coupon);
      setStep("coupon");
    } catch (x) {
      if (x instanceof ApiFailure && x.status === 401) {
        onSessionExpired();
        return;
      }
      setError(x instanceof Error ? x.message : "Coupon was not found.");
      setStep("start");
    }
  }, [onSessionExpired]);
  async function startScanner() {
    setError("");
    setStep("scan");
    await new Promise((r) => setTimeout(r, 50));
    if (!video.current) return;
    try {
      const reader = new BrowserQRCodeReader();
      controls.current = await reader.decodeFromVideoDevice(
        undefined,
        video.current,
        (result) => {
          if (result) {
            controls.current?.stop();
            void lookup(result.getText());
          }
        },
      );
    } catch {
      setError("Camera access is unavailable. Use participant code instead.");
      setStep("start");
    }
  }
  useEffect(() => () => controls.current?.stop(), []);
  async function pay(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!wallet) return;
    const f = new FormData(e.currentTarget);
    try {
      const result = await api<{
        transaction: { status: string; reference: string };
      }>(
        `/vendor/payments`,
        {
          method: "POST",
          body: JSON.stringify({
            wallet_id: wallet.id,
            qr_token: paymentToken,
            participant_code: paymentToken ? null : wallet.participant_code,
            amount_minor: Math.round(Number(f.get("amount")) * 100),
            request_key: crypto.randomUUID(),
          }),
        },
        csrf,
      );
      setMessage(
        result.transaction.status === "pending"
          ? `Payment ${result.transaction.reference} is waiting for participant approval.`
          : `Payment ${result.transaction.reference} completed.`,
      );
      setStep("result");
    } catch (x) {
      if (x instanceof ApiFailure && x.status === 401) {
        onSessionExpired();
        return;
      }
      setError(x instanceof Error ? x.message : "Payment failed.");
    }
  }
  async function redeem() {
    if (!coupon) return;
    try {
      const r = await api<{ redemption: { reference: string } }>(
        `/vendor/coupons/redeem`,
        {
          method: "POST",
          body: JSON.stringify(coupon.token ? { token: coupon.token } : { code: coupon.code }),
        },
        csrf,
      );
      setMessage(`Coupon redeemed. Reference ${r.redemption.reference}.`);
      setStep("result");
    } catch (x) {
      if (x instanceof ApiFailure && x.status === 401) {
        onSessionExpired();
        return;
      }
      setError(x instanceof Error ? x.message : "Redemption failed.");
    }
  }
  function reset() {
    setWallet(null);
    setPaymentToken(null);
    setCoupon(null);
    setError("");
    setMessage("");
    setStep("start");
  }
  return (
    <PublicShell>
      <section className="mx-auto max-w-[720px] px-5 pb-16 pt-6">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-wide text-leaf-700">
              {vendor.event_name}
            </p>
            <h1 className="text-2xl font-bold">{vendor.name}</h1>
          </div>
          <button
            className="button-secondary min-h-9"
            onClick={() => void onLogout()}
          >
            <LogOut size={16} /> Sign out
          </button>
        </div>
        <div className="card overflow-hidden">
          {step !== "start" && step !== "result" && (
            <button
              className="m-4 flex items-center gap-1 text-sm font-semibold text-black/50"
              onClick={reset}
            >
              <ArrowLeft size={16} /> Back
            </button>
          )}
          {error && (
            <div className="alert-error mx-5 mt-5 text-sm">
              {error}
            </div>
          )}
          {step === "start" && (
            <Start
              onScan={() => void startScanner()}
              onLookup={(code) => void lookup(code, true)}
              onCouponLookup={(code) => void lookupCouponCode(code)}
            />
          )}{" "}
          {step === "scan" && (
            <div className="p-5 pt-0">
              <div className="wallet-scanner">
                <video
                  ref={video}
                  className="aspect-square w-full object-cover"
                />
                <div className="pointer-events-none absolute inset-10 rounded-3xl border-2 border-white/80" />
                <div className="wallet-scan-line" />
              </div>
              <button
                className="button-secondary mt-4 w-full"
                onClick={() => {
                  controls.current?.stop();
                  reset();
                }}
              >
                <X size={18} /> Cancel scan
              </button>
            </div>
          )}{" "}
          {step === "wallet" && wallet && (
            <form onSubmit={pay} className="p-6 pt-2">
              <span className="badge">Payment</span>
              <h2 className="mt-3 text-3xl font-bold">
                {wallet.participant_name}
              </h2>
              <p className="text-black/50">
                {wallet.participant_code} · {wallet.group || "No group"}
              </p>
              <div className="my-6 rounded-lg bg-leaf-50 p-5">
                <p className="text-sm text-leaf-700">Available</p>
                <p className="text-4xl font-bold text-leaf-700">
                  {money(
                    wallet.balance_minor - wallet.reserved_minor,
                    wallet.currency,
                  )}
                </p>
              </div>
              {!!wallet.coupons.length && (
                <div className="mb-6">
                  <p className="label">Coupons</p>
                  <div className="mt-2 grid gap-2">
                    {wallet.coupons.map((item) => (
                      <button
                        type="button"
                        key={item.code}
                        disabled={item.status !== "available"}
                        className="button-secondary justify-between"
                        onClick={() => { setCoupon(item); setStep("coupon"); }}
                      >
                        <span>{item.name}</span>
                        <span className="text-xs uppercase">{item.status}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <label className="label">Amount</label>
              <input
                className="input text-2xl font-bold"
                name="amount"
                type="number"
                min="0.01"
                max={(wallet.balance_minor - wallet.reserved_minor) / 100}
                step="0.01"
                required
              />
              <button className="button mt-4 w-full">Confirm payment</button>
            </form>
          )}{" "}
          {step === "coupon" && coupon && (
            <div className="p-6 pt-2">
              <span className="badge">Coupon</span>
              <h2 className="mt-3 text-3xl font-bold">{coupon.name}</h2>
              <p className="mt-1 text-black/50">
                Issued to {coupon.participant_name}
              </p>
              <p className="mt-2 font-mono text-sm font-semibold">{coupon.code}</p>
              <div className="alert-warning my-6 text-sm">
                A redeemed coupon cannot be used again.
              </div>
              <button className="button w-full" onClick={() => void redeem()}>
                Redeem coupon
              </button>
            </div>
          )}{" "}
          {step === "result" && (
            <div className="p-8 text-center">
              <CheckCircle2 className="mx-auto text-leaf-600" size={58} />
              <h2 className="mt-4 text-3xl font-bold">Complete</h2>
              <p className="mx-auto mt-2 max-w-md text-black/55">{message}</p>
              <button className="button mt-6" onClick={reset}>
                Next participant
              </button>
            </div>
          )}
        </div>
      </section>
    </PublicShell>
  );
}

function Start({
  onScan,
  onLookup,
  onCouponLookup,
}: {
  onScan: () => void;
  onLookup: (code: string) => void;
  onCouponLookup: (code: string) => void;
}) {
  const [code, setCode] = useState("");
  const [couponCode, setCouponCode] = useState("");
  return (
    <div className="p-6">
      <h2 className="text-3xl font-semibold">
        Scan a participant
      </h2>
      <p className="mt-2 text-black/55">
        Scan a payment or coupon QR code. Participant code is available as a
        fallback.
      </p>
      <button className="button mt-7 h-16 w-full text-lg" onClick={onScan}>
        <Camera /> Open camera
      </button>
      <div className="my-6 flex items-center gap-3 text-xs uppercase tracking-widest text-black/35">
        <span className="h-px flex-1 bg-black/10" />
        or use code
        <span className="h-px flex-1 bg-black/10" />
      </div>
      <div className="flex gap-2">
        <input
          className="input"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="Participant code"
        />
        <button
          className="button-secondary"
          disabled={!code.trim()}
          onClick={() => onLookup(code.trim())}
        >
          <Search size={18} />
        </button>
      </div>
      <label className="label mt-5">Coupon code</label>
      <div className="flex gap-2">
        <input
          className="input font-mono uppercase"
          value={couponCode}
          onChange={(e) => setCouponCode(e.target.value.toUpperCase())}
          placeholder="CP-…"
        />
        <button
          className="button-secondary"
          disabled={!couponCode.trim()}
          onClick={() => onCouponLookup(couponCode.trim())}
        >
          <Ticket size={18} />
        </button>
      </div>
    </div>
  );
}
