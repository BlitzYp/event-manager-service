import {
  Archive,
  BadgeCheck,
  Ban,
  CalendarClock,
  CheckCheck,
  CircleCheckBig,
  CircleOff,
  Clock3,
  FileClock,
  PauseCircle,
  Undo2,
  XCircle,
} from "lucide-react";

const statusMeta = {
  draft: { className: "status-badge--draft", Icon: FileClock },
  active: { className: "status-badge--active", Icon: CircleCheckBig },
  archived: { className: "status-badge--archived", Icon: Archive },
  disabled: { className: "status-badge--disabled", Icon: CircleOff },
  scheduled: { className: "status-badge--scheduled", Icon: CalendarClock },
  completed: { className: "status-badge--completed", Icon: CheckCheck },
  suspended: { className: "status-badge--suspended", Icon: PauseCircle },
  pending: { className: "status-badge--pending", Icon: Clock3 },
  approved: { className: "status-badge--approved", Icon: BadgeCheck },
  rejected: { className: "status-badge--rejected", Icon: XCircle },
  cancelled: { className: "status-badge--cancelled", Icon: Ban },
  reversed: { className: "status-badge--reversed", Icon: Undo2 },
} as const;

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const normalized = status.toLowerCase() as keyof typeof statusMeta;
  const meta = statusMeta[normalized] ?? statusMeta.archived;
  const Icon = meta.Icon;
  return (
    <span className={`badge gap-1.5 ${meta.className}`}>
      <Icon size={13} aria-hidden="true" />
      <span>{label ?? status}</span>
    </span>
  );
}
