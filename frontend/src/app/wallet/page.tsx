"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Store } from "lucide-react";
import { PublicShell } from "@/components/Shell";
import { VendorConsole } from "@/components/vendor/VendorConsole";
import type { Vendor } from "@/components/vendor/types";
import { ApiFailure, api } from "@/lib/api";

/** Restore a vendor session or sign in, then render the event-specific checkout console. */
export default function VendorWalletPage() {
  const [vendor, setVendor] = useState<Vendor | null>(null);
  const [csrf, setCsrf] = useState("");
  const [error, setError] = useState("");
  /** Restore a vendor session and obtain its CSRF token, or return to sign-in. */
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
  /** Submit the event code and PIN, then store vendor identity and CSRF for checkout. */
  async function login(submitEvent: FormEvent<HTMLFormElement>) {
    submitEvent.preventDefault();
    setError("");
    const form = new FormData(submitEvent.currentTarget);
    try {
      const result = await api<{ vendor: Vendor; csrf_token: string }>(
        "/vendor/login",
        {
          method: "POST",
          body: JSON.stringify({
            event_code: form.get("event_code"),
            pin: form.get("pin"),
          }),
        },
      );
      setVendor(result.vendor);
      setCsrf(result.csrf_token);
    } catch (failure) {
      setError(failure instanceof ApiFailure ? failure.message : "Sign in failed.");
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
