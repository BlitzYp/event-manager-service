"use client";

import Link from "next/link";
import { type FormEvent, useCallback, useEffect, useState } from "react";
import { LogOut, RefreshCw, Smartphone, WalletCards } from "lucide-react";
import { EventWorkspace } from "@/components/admin/EventWorkspace";
import type { Event } from "@/components/admin/types";
import { Brand } from "@/components/Shell";
import { ApiFailure, api, money } from "@/lib/api";

type AdminIdentity = {
  email: string;
  is_super_admin: boolean;
  is_active: boolean;
  impersonating: boolean;
};

export default function AdminPage() {
  const [authChecked, setAuthChecked] = useState(false);
  const [user, setUser] = useState<AdminIdentity | null>(null);
  const [csrf, setCsrf] = useState("");
  const [error, setError] = useState("");
  const [events, setEvents] = useState<Event[]>([]);
  const [eventId, setEventId] = useState<number>();
  const [registering, setRegistering] = useState(false);

  const bootstrap = useCallback(async () => {
    try {
      const me = await api<{ user: AdminIdentity }>("/auth/me");
      const token = await api<{ csrf_token: string }>("/auth/csrf", { method: "POST" });
      setUser(me.user);
      setCsrf(token.csrf_token);
      if (!me.user.is_active) {
        setEvents([]);
        setEventId(undefined);
        return;
      }
      const result = await api<{ events: Event[] }>("/admin/events");
      setEvents(result.events);
      setEventId((current) =>
        current && result.events.some((event) => event.id === current)
          ? current
          : result.events[0]?.id,
      );
    } catch {
      setUser(null);
      setCsrf("");
      setEvents([]);
      setEventId(undefined);
    } finally {
      setAuthChecked(true);
    }
  }, []);

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  useEffect(() => {
    if (!user) return;
    const interval = window.setInterval(async () => {
      try {
        const result = await api<{ user: AdminIdentity }>("/auth/me");
        if (!result.user.is_active && user.is_active) {
          setUser(result.user);
          setEvents([]);
          setEventId(undefined);
        } else if (result.user.is_active && !user.is_active) {
          await bootstrap();
        }
      } catch {
        // A transient status-check failure should not discard the current page.
      }
    }, 15_000);
    return () => window.clearInterval(interval);
  }, [bootstrap, user]);

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const result = await api<{ user: AdminIdentity; csrf_token: string }>(
        registering ? "/auth/register" : "/auth/login",
        {
          method: "POST",
          body: JSON.stringify({ email: form.get("email"), password: form.get("password") }),
        },
      );
      setUser(result.user);
      setCsrf(result.csrf_token);
      await bootstrap();
    } catch (failure) {
      setError(failure instanceof ApiFailure ? failure.message : "Sign in failed.");
    }
  }

  if (!authChecked) {
    return (
      <main className="grid min-h-screen place-items-center bg-[#e9ecef]" aria-live="polite">
        <div className="flex items-center gap-3 text-sm font-medium text-black/55">
          <RefreshCw className="animate-spin" size={20} aria-hidden="true" />
          Checking administrator session…
        </div>
      </main>
    );
  }

  if (!user) {
    return (
      <main className="grid min-h-screen place-items-center bg-[#e9ecef] px-4 py-10">
        <form onSubmit={login} className="card w-full max-w-md p-7 md:p-8">
          <div className="-mx-7 -mt-7 mb-7 rounded-t-lg bg-gradient-to-br from-[#397c22] to-leaf-600 px-7 py-5 text-white md:-mx-8 md:-mt-8 md:px-8">
            <Brand />
          </div>
          <span className="wallet-icon mb-3"><WalletCards size={22} /></span>
          <h1 className="text-3xl font-semibold">{registering ? "Create administrator account" : "Administrator sign in"}</h1>
          <p className="mt-2 text-sm text-black/55">Create and manage your own events, participants and vendors.</p>
          {error && <p className="alert-error mt-5 text-sm">{error}</p>}
          <label className="label mt-6">Email</label>
          <input className="input" name="email" type="email" required autoComplete="email" />
          <label className="label mt-4">Password</label>
          <input className="input" name="password" type="password" minLength={registering ? 12 : 8} required autoComplete={registering ? "new-password" : "current-password"} />
          <button className="button mt-6 w-full">{registering ? "Create account" : "Sign in"}</button>
          <button type="button" className="mt-4 w-full text-sm font-semibold text-leaf-700" onClick={() => { setRegistering(!registering); setError(""); }}>
            {registering ? "Already have an account? Sign in" : "Need an account? Register"}
          </button>
        </form>
      </main>
    );
  }

  const selected = events.find((item) => item.id === eventId);
  return (
    <div className="min-h-screen bg-[#f8f9fa]">
      <header className="bg-[#212529] text-white shadow-sm">
        <div className="mx-auto flex max-w-[1440px] items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <Brand />
          <div className="flex items-center gap-2 text-sm">
            <span className="hidden text-white/75 md:block">{user.email}</span>
            <button
              className="inline-flex min-h-9 items-center gap-2 rounded-md bg-white px-3 py-2 font-semibold text-[#212529] hover:bg-white/90"
              onClick={async () => {
                await api("/auth/logout", { method: "POST" }, csrf);
                setUser(null);
              }}
            >
              <LogOut size={16} /> <span className="hidden sm:inline">Sign out</span>
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1440px] px-4 py-10 sm:px-6">
        {!user.is_active ? (
          <div className="alert-warning mx-auto max-w-3xl p-6">
            <h1 className="text-xl font-semibold">Administrator account disabled</h1>
            <p className="mt-2 text-sm">Your account has been disabled by a super-admin. Event data, transaction history, exports, and administrative actions are unavailable. Contact a super-admin to restore access.</p>
          </div>
        ) : (<>
        {user.impersonating && <div className="alert-warning mb-5 flex items-center justify-between gap-3 text-sm"><span>You are viewing this account as super-admin.</span><button className="button-secondary min-h-9" onClick={async () => { await api("/auth/stop-impersonating", { method: "POST" }, csrf); await bootstrap(); }}>Return to super-admin</button></div>}
        <div className="mb-6 flex flex-col justify-between gap-4 md:flex-row md:items-center">
          <div>
            <h1 className="text-3xl font-semibold">Virtual wallet</h1>
            <p className="mt-1 text-black/50">
              {selected?.name || "Create or select an event to begin"}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link className="button-secondary" href="/wallet" target="_blank">
              <Smartphone size={17} /> Vendor portal
            </Link>
            <select
              className="input min-w-56"
              value={eventId ?? ""}
              onChange={(event) => setEventId(Number(event.target.value))}
              aria-label="Selected event"
            >
              <option value="">Select an event</option>
              {events.map((item) => (
                <option key={item.id} value={item.id}>{item.name} · {item.status}</option>
              ))}
            </select>
            <button className="button-secondary px-3" onClick={() => void bootstrap()} aria-label="Refresh">
              <RefreshCw size={18} />
            </button>
          </div>
        </div>

        {selected && (
          <div className="mb-6 grid gap-4 md:grid-cols-3">
            <Stat label="Event status" value={selected.status} />
            <Stat label="Systems" value={selected.mode === "both" ? "Money + coupons" : selected.mode} />
            <Stat
              accent
              label="Default wallet balance"
              value={money(selected.default_balance_minor, selected.currency)}
            />
          </div>
        )}

        <EventWorkspace
          key={`${user.email}:${user.impersonating}`}
          event={selected}
          events={events}
          csrf={csrf}
          onSelectEvent={setEventId}
          onEventsChanged={bootstrap}
          isSuperAdmin={user.is_super_admin && !user.impersonating}
          onImpersonated={bootstrap}
        />
        </>)}
      </main>
    </div>
  );
}

function Stat({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className={`card p-5 ${accent ? "bg-leaf-600 text-black" : ""}`}>
      <small className={accent ? "text-black/80" : "text-black/50"}>{label}</small>
      <div className="mt-1 text-2xl font-semibold capitalize">{value}</div>
    </div>
  );
}
