import type { FormEvent } from "react";
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiFailure, api } from "@/lib/api";
import { useVendorConsole } from "./useVendorConsole";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/api")>(),
  api: vi.fn(),
}));

const mockedApi = vi.mocked(api);
const wallet = {
  id: 7,
  participant_code: "P 1",
  participant_name: "Example participant",
  balance_minor: 2500,
  reserved_minor: 0,
  currency: "EUR",
  coupons: [],
};

describe("useVendorConsole", () => {
  beforeEach(() => {
    mockedApi.mockReset();
  });

  it("looks up an encoded participant code and resets checkout", async () => {
    mockedApi.mockResolvedValueOnce({ kind: "wallet", wallet });
    const { result } = renderHook(() => useVendorConsole("csrf", vi.fn()));

    await act(async () => { await result.current.lookup("P 1", true); });

    expect(mockedApi).toHaveBeenCalledWith("/vendor/lookup?participant_code=P%201");
    expect(result.current.wallet).toEqual(wallet);
    expect(result.current.step).toBe("wallet");

    act(() => result.current.reset());

    expect(result.current.wallet).toBeNull();
    expect(result.current.step).toBe("start");
  });

  it("submits a QR payment in minor units with a request key and CSRF", async () => {
    mockedApi.mockResolvedValueOnce({ kind: "wallet", wallet });
    mockedApi.mockResolvedValueOnce({ transaction: { status: "pending", reference: "PAY-123" } });
    const { result } = renderHook(() => useVendorConsole("csrf", vi.fn()));
    await act(async () => { await result.current.lookup("example-payment-token"); });
    const form = document.createElement("form");
    const amount = document.createElement("input");
    amount.name = "amount";
    amount.value = "12.34";
    form.append(amount);

    await act(async () => {
      await result.current.pay({
        preventDefault: vi.fn(), currentTarget: form,
      } as unknown as FormEvent<HTMLFormElement>);
    });

    expect(mockedApi).toHaveBeenLastCalledWith(
      "/vendor/payments", expect.objectContaining({ method: "POST" }), "csrf",
    );
    const paymentRequest = mockedApi.mock.calls.at(-1)?.[1];
    expect(JSON.parse(String(paymentRequest?.body))).toEqual({
      wallet_id: 7, qr_token: "example-payment-token", participant_code: null,
      amount_minor: 1234, request_key: expect.any(String),
    });
    expect(result.current.step).toBe("result");
    expect(result.current.message).toContain("waiting for participant approval");
  });

  it("returns to sign-in on an expired lookup session", async () => {
    mockedApi.mockRejectedValueOnce(new ApiFailure(401, "authentication_required", "Expired"));
    const onSessionExpired = vi.fn();
    const { result } = renderHook(() => useVendorConsole("csrf", onSessionExpired));

    await act(async () => { await result.current.lookupCouponCode("CP-EXAMPLE"); });

    expect(onSessionExpired).toHaveBeenCalledOnce();
    expect(result.current.error).toBe("");
  });

  it("redeems a manually entered coupon by code with CSRF", async () => {
    mockedApi.mockResolvedValueOnce({
      kind: "coupon",
      coupon: { code: "CP-EXAMPLE", name: "Lunch", status: "available", participant_name: "Guest" },
    });
    mockedApi.mockResolvedValueOnce({ redemption: { reference: "CPA-123" } });
    const { result } = renderHook(() => useVendorConsole("csrf", vi.fn()));

    await act(async () => { await result.current.lookupCouponCode("CP-EXAMPLE"); });
    await act(async () => { await result.current.redeem(); });

    expect(mockedApi).toHaveBeenLastCalledWith(
      "/vendor/coupons/redeem",
      { method: "POST", body: JSON.stringify({ code: "CP-EXAMPLE" }) },
      "csrf",
    );
    expect(result.current.step).toBe("result");
    expect(result.current.message).toContain("CPA-123");
  });

  it("stops the active camera reader when the console unmounts", () => {
    const stop = vi.fn();
    const { result, unmount } = renderHook(() => useVendorConsole("csrf", vi.fn()));
    result.current.controls.current = { stop };

    unmount();

    expect(stop).toHaveBeenCalledOnce();
  });
});
