"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { BrowserQRCodeReader, IScannerControls } from "@zxing/browser";
import { ApiFailure, api } from "@/lib/api";
import type { Coupon, Wallet } from "./types";

/** Own checkout state, scanner cleanup, API mutations, and session-expiry handling. */
export function useVendorConsole(csrf: string, onSessionExpired: () => void) {
  // Current checkout step, target, and customer-facing result/error messages.
  const [step, setStep] = useState<
    "start" | "scan" | "wallet" | "coupon" | "result"
  >("start");
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [paymentToken, setPaymentToken] = useState<string | null>(null);
  const [coupon, setCoupon] = useState<Coupon | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  // Camera handles live in refs so rendering does not recreate the active reader.
  const video = useRef<HTMLVideoElement>(null);
  const controls = useRef<IScannerControls | undefined>(undefined);
  // Session watchdog: revoke the screen and stop capture when authentication fails.
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
  /**
   * Resolve a payment QR or participant code to a wallet/coupon and move checkout to the matching step.
   */
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
    } catch (failure) {
      if (failure instanceof ApiFailure && failure.status === 401) {
        onSessionExpired();
        return;
      }
      setError(failure instanceof Error ? failure.message : "Nothing was found.");
      setStep("start");
    }
  }, [onSessionExpired]);
  /** Resolve a human-entered coupon code and open its redemption step. */
  const lookupCouponCode = useCallback(async (value: string) => {
    setError("");
    try {
      const result = await api<{ kind: "coupon"; coupon: Coupon }>(
        `/vendor/lookup?coupon_code=${encodeURIComponent(value)}`,
      );
      setCoupon(result.coupon);
      setStep("coupon");
    } catch (failure) {
      if (failure instanceof ApiFailure && failure.status === 401) {
        onSessionExpired();
        return;
      }
      setError(failure instanceof Error ? failure.message : "Coupon was not found.");
      setStep("start");
    }
  }, [onSessionExpired]);
  /** Mount the scan view, start the QR camera reader, and stop capture after a decoded result. */
  async function startScanner() {
    setError("");
    setStep("scan");
    await new Promise((resolve) => setTimeout(resolve, 50));
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
  /** Send an idempotent payment in integer minor units and display its approval/completion result. */
  async function pay(submitEvent: FormEvent<HTMLFormElement>) {
    submitEvent.preventDefault();
    if (!wallet) return;
    const form = new FormData(submitEvent.currentTarget);
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
            amount_minor: Math.round(Number(form.get("amount")) * 100),
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
    } catch (failure) {
      if (failure instanceof ApiFailure && failure.status === 401) {
        onSessionExpired();
        return;
      }
      setError(failure instanceof Error ? failure.message : "Payment failed.");
    }
  }
  /** Redeem the selected coupon by token or code and display its audit reference. */
  async function redeem() {
    if (!coupon) return;
    try {
      const result = await api<{ redemption: { reference: string } }>(
        `/vendor/coupons/redeem`,
        {
          method: "POST",
          body: JSON.stringify(coupon.token ? { token: coupon.token } : { code: coupon.code }),
        },
        csrf,
      );
      setMessage(`Coupon redeemed. Reference ${result.redemption.reference}.`);
      setStep("result");
    } catch (failure) {
      if (failure instanceof ApiFailure && failure.status === 401) {
        onSessionExpired();
        return;
      }
      setError(failure instanceof Error ? failure.message : "Redemption failed.");
    }
  }
  /** Clear the current wallet, coupon, messages, and QR selection before the next participant. */
  function reset() {
    setWallet(null);
    setPaymentToken(null);
    setCoupon(null);
    setError("");
    setMessage("");
    setStep("start");
  }
  return {
    step, wallet, coupon, message, error,
    video, controls,
    lookup, lookupCouponCode, startScanner,
    pay, redeem, reset, setCoupon, setStep,
  };
}
