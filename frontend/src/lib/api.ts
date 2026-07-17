const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api/v1";

export class ApiFailure extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
}

export async function api<T>(path: string, init: RequestInit = {}, csrf?: string): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (csrf) headers.set("X-CSRF-Token", csrf);
  const response = await fetch(`${BASE}${path}`, { ...init, headers, credentials: "include", cache: "no-store" });
  const contentType = response.headers.get("content-type") ?? "";
  if (!response.ok) {
    const body = contentType.includes("json") ? await response.json() : null;
    throw new ApiFailure(response.status, body?.error?.code ?? "request_failed", body?.error?.message ?? "Request failed.");
  }
  return (contentType.includes("json") ? response.json() : response) as Promise<T>;
}

export function money(minor: number, currency: string) {
  return new Intl.NumberFormat("en", { style: "currency", currency }).format(minor / 100);
}

