"use client";

import { useState } from "react";
import { Camera, Search, Ticket } from "lucide-react";

/** Collect a QR scan request, participant code, or coupon code without calling the API. */
export function VendorStart({
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
