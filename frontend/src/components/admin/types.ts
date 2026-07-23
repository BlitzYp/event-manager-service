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
  coupons: {
    available: number;
    disabled: number;
    redeemed: number;
    total: number;
  };
};

export type Vendor = {
  id: number;
  name: string;
  contract_number?: string | null;
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
  kind: "money";
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

export type CouponTransaction = {
  kind: "coupon";
  id: number;
  reference: string;
  action: string;
  coupon_name: string;
  participant_code: string;
  participant_name: string;
  vendor_id?: number | null;
  vendor_name?: string | null;
  actor: string;
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
  auto_delete: boolean;
  enabled: boolean;
  completed_at?: string;
  run_count: number;
  email_template_id?: number | null;
  email_subject?: string | null;
};

export type EmailBlock = {
  type: string;
  data: {
    props?: Record<string, unknown>;
    style?: Record<string, unknown>;
    childrenIds?: string[];
    [key: string]: unknown;
  };
};

export type EmailDocument = Record<string, EmailBlock>;

export type EmailTemplate = {
  id: number;
  event_id: number;
  name: string;
  subject: string;
  version: number;
  archived_at?: string | null;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
  document?: EmailDocument;
  rendered_html?: string;
};

export type EmailAsset = {
  id: number;
  original_name: string;
  mime_type: string;
  file_size: number;
  width: number;
  height: number;
  created_at: string;
  url: string;
};

export type EmailDelivery = {
  id: number;
  template_id?: number | null;
  participant_id?: number | null;
  recipient_email: string;
  recipient_name?: string | null;
  subject: string;
  status: "sent" | "failed" | "simulated";
  error?: string | null;
  created_at: string;
  sent_at?: string | null;
};
