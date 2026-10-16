"use client";

import { ArrowLeft, CheckCircle2, LogOut, X } from "lucide-react";
import { PublicShell } from "@/components/Shell";
import { money } from "@/lib/api";
import { VendorStart } from "./VendorStart";
import { useVendorConsole } from "./useVendorConsole";
import type { Vendor } from "./types";

/** Display scan, payment, coupon redemption, and completion steps for one signed-in vendor. */
export function VendorConsole({
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
  const {
    step, wallet, coupon, message, error,
    video, controls,
    lookup, lookupCouponCode, startScanner,
    pay, redeem, reset, setCoupon, setStep,
  } = useVendorConsole(csrf, onSessionExpired);
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
            <VendorStart
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
              <p className="mt-2 font-mono text-sm font-semibold">{coupon.code}</p>
              <p className="mt-3 text-sm text-black/50">
                Vendor: {vendor.name} · Contract: {vendor.contract_number || "—"}
              </p>
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
