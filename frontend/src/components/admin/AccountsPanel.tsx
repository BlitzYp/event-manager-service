"use client";

import { useCallback, useEffect, useState } from "react";
import { LogIn, Power } from "lucide-react";
import { api } from "@/lib/api";
import { Empty } from "./AdminUi";
import { StatusBadge } from "./StatusBadge";

type Account = {
  id: number;
  email: string;
  is_active: boolean;
  is_super_admin: boolean;
  event_count: number;
  created_at: string;
};

export function AccountsPanel({ csrf, onImpersonated }: { csrf: string; onImpersonated: () => Promise<void> }) {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [totals, setTotals] = useState({ admins: 0, events: 0 });
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try {
      const result = await api<{ accounts: Account[]; totals: typeof totals }>("/admin/accounts");
      setAccounts(result.accounts);
      setTotals(result.totals);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not load accounts.");
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function setActive(account: Account) {
    setError("");
    try {
      await api(`/admin/accounts/${account.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !account.is_active }),
      }, csrf);
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not update the account.");
    }
  }

  return (
    <section className="mb-6">
      <div className="mb-3 flex items-end justify-between">
        <div><h2 className="text-xl font-semibold">Administrator accounts</h2><p className="text-sm text-black/50">{totals.admins} accounts · {totals.events} events</p></div>
      </div>
      {error && <div className="alert-error mb-3 text-sm">{error}</div>}
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {accounts.map((account) => (
          <article className="card p-4" key={account.id}>
            <div className="flex items-start justify-between gap-2"><strong className="break-all">{account.email}</strong><StatusBadge status={account.is_active ? "active" : "disabled"} /></div>
            <p className="mt-2 text-sm text-black/50">{account.event_count} event{account.event_count === 1 ? "" : "s"} · {account.is_super_admin ? "Super-admin" : "Administrator"}</p>
            {!account.is_super_admin && <div className="mt-3 flex flex-wrap gap-2">
              {account.is_active && <button className="button-secondary min-h-9" onClick={async () => { await api(`/admin/accounts/${account.id}/impersonate`, { method: "POST" }, csrf); await onImpersonated(); }}><LogIn size={15} /> Log in as user</button>}
              <button className="button-secondary min-h-9" onClick={() => void setActive(account)}><Power size={15} /> {account.is_active ? "Disable" : "Enable"}</button>
            </div>}
          </article>
        ))}
        {!accounts.length && <Empty text="No administrator accounts." />}
      </div>
    </section>
  );
}
