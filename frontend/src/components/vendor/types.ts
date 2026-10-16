/** API response shapes shared by the vendor sign-in, lookup, and checkout screens. */
export type Vendor = {
  id: number;
  name: string;
  contract_number?: string | null;
  event_id: number;
  event_name: string;
};
export type Wallet = {
  id: number;
  participant_code: string;
  participant_name: string;
  group?: string;
  balance_minor: number;
  reserved_minor: number;
  currency: string;
  coupons: Coupon[];
};
export type Coupon = {
  token?: string | null;
  code: string;
  name: string;
  status: string;
  participant_name: string;
};

