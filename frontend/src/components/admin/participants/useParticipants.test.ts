import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import type { Event } from "../types";
import { useParticipants } from "./useParticipants";

vi.mock("@/lib/api", () => ({ api: vi.fn() }));

const mockedApi = vi.mocked(api);
const event: Event = {
  id: 4, code: "demo", name: "Demo", status: "active", mode: "money", currency: "EUR",
  default_balance_minor: 0, approval_required: true, qr_ttl_seconds: 60, pending_payment_minutes: 5,
};
const participant = {
  id: 8, participant_code: "P-1", name: "Guest", group: "Guests",
  wallet: { id: 12, balance_minor: 0, reserved_minor: 0, enabled: true },
  coupons: { available: 0, disabled: 0, redeemed: 0, total: 0 },
};

describe("useParticipants", () => {
  beforeEach(() => {
    mockedApi.mockReset();
    mockedApi.mockImplementation(async (path) => {
      if (path.includes("/participants")) return { participants: [participant], groups: ["Guests"] };
      return { actions: [] };
    });
  });

  it("applies filters only on request and clears stale wallet selection", async () => {
    const { result } = renderHook(() => useParticipants(event, "csrf"));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    const initialCalls = mockedApi.mock.calls.length;

    act(() => {
      result.current.setDraftFilters({ search: "Guest", group: "Guests", wallet_status: "active" });
      result.current.setSelectedWalletIds(new Set([12]));
    });
    expect(mockedApi.mock.calls).toHaveLength(initialCalls);

    act(() => result.current.setAppliedFilters(result.current.draftFilters));

    await waitFor(() => expect(mockedApi).toHaveBeenCalledWith(
      "/admin/events/4/participants?search=Guest&group=Guests&wallet_status=active",
    ));
    await waitFor(() => expect(result.current.selectedWalletIds.size).toBe(0));
  });

  it("scopes an automation to the selected event wallets", async () => {
    const { result } = renderHook(() => useParticipants(event, "csrf"));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    act(() => {
      result.current.setBulkActionId("9");
      result.current.setBulkScope("selected");
      result.current.setBulkOperation("exclude");
      result.current.setSelectedWalletIds(new Set([12]));
    });
    mockedApi.mockResolvedValueOnce({ message: "1 wallet excluded." });

    await act(async () => { await result.current.applyBulkAction(); });

    expect(mockedApi).toHaveBeenCalledWith(
      "/admin/events/4/actions/9/wallet-scope",
      { method: "POST", body: JSON.stringify({ operation: "exclude", wallet_ids: [12] }) },
      "csrf",
    );
    expect(result.current.notice).toBe("1 wallet excluded.");
  });

  it("rotates a participant link without opening or replacing a preview", async () => {
    const { result } = renderHook(() => useParticipants(event, "csrf"));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    mockedApi.mockResolvedValueOnce({ wallet_link: "https://example.com/wallet/replacement" });

    await act(async () => { await result.current.rotateWalletLink(participant); });

    expect(mockedApi).toHaveBeenLastCalledWith(
      "/admin/events/4/participants/8/rotate-wallet-link", { method: "POST" }, "csrf",
    );
    expect(result.current.notice).toContain("Replacement link (shown once)");
  });
});
