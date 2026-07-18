export type Event = {
  id: number;
  code: string;
  name: string;
  status: "draft" | "active" | "archived";
  mode: "money" | "coupons" | "both";
  currency: string;
  default_balance_minor: number;
  approval_required: boolean;
  qr_ttl_seconds: number;
  pending_payment_minutes: number;
};

export type Participant = {
  id: number;
  participant_code: string;
  name: string;
  group?: string | null;
  email?: string | null;
  wallet: {
    id: number;
    balance_minor: number;
    reserved_minor: number;
    enabled: boolean;
  };
};

export type Vendor = {
  id: number;
  name: string;
  active: boolean;
  last_login_at?: string;
};

export type CouponTemplate = {
  id: number;
  name: string;
  vendor_id?: number;
  sort_order: number;
  active: boolean;
};

export type Transaction = {
  id: number;
  reference: string;
  type: string;
  status: string;
  amount_minor: number;
  participant_code: string;
  participant_name: string;
  group?: string | null;
  vendor_id?: number | null;
  vendor_name?: string;
  created_at: string;
};

export type ScheduledAction = {
  id: number;
  name: string;
  action_type: string;
  schedule_type: string;
  execute_at: string;
  schedule_start?: string;
  schedule_end?: string;
  schedule_time?: string;
  enabled: boolean;
  completed_at?: string;
};
