from __future__ import annotations

import enum
from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base, utcnow


class EventStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    archived = "archived"


class EventMode(str, enum.Enum):
    money = "money"
    coupons = "coupons"
    both = "both"


class TransactionStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"
    reversed = "reversed"


class TransactionType(str, enum.Enum):
    initial_credit = "initial_credit"
    admin_credit = "admin_credit"
    admin_debit = "admin_debit"
    vendor_debit = "vendor_debit"
    reversal = "reversal"


class CouponStatus(str, enum.Enum):
    available = "available"
    disabled = "disabled"
    redeemed = "redeemed"
    removed = "removed"


class ActionType(str, enum.Enum):
    create_wallets = "create_wallets"
    activate_wallets = "activate_wallets"
    deactivate_wallets = "deactivate_wallets"
    delete_wallets = "delete_wallets"
    issue_coupons = "issue_coupons"
    refill_coupons = "refill_coupons"
    disable_coupons = "disable_coupons"
    enable_coupons = "enable_coupons"
    send_email = "send_email"


class ScheduleType(str, enum.Enum):
    once = "once"
    daily = "daily"


class EmailDeliveryStatus(str, enum.Enum):
    sent = "sent"
    failed = "failed"
    simulated = "simulated"


class IdMixin:
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class AdminUser(IdMixin, TimestampMixin, Base):
    __tablename__ = "admin_users"
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_super_admin: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class AdminSession(IdMixin, Base):
    __tablename__ = "admin_sessions"
    admin_id: Mapped[int] = mapped_column(
        ForeignKey("admin_users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    impersonator_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    admin: Mapped[AdminUser] = relationship(foreign_keys=[admin_id])


class Event(IdMixin, TimestampMixin, Base):
    __tablename__ = "events"
    admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="RESTRICT"), index=True
    )
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[EventStatus] = mapped_column(
        Enum(EventStatus, native_enum=False), default=EventStatus.draft
    )
    mode: Mapped[EventMode] = mapped_column(Enum(EventMode, native_enum=False))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    default_balance_minor: Mapped[int] = mapped_column(BigInteger, default=5000)
    qr_ttl_seconds: Mapped[int] = mapped_column(Integer, default=60)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=True)
    pending_payment_minutes: Mapped[int] = mapped_column(Integer, default=5)


class Participant(IdMixin, TimestampMixin, Base):
    __tablename__ = "participants"
    __table_args__ = (UniqueConstraint("event_id", "participant_code"),)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    participant_code: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(255))
    group_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    event: Mapped[Event] = relationship()
    wallet: Mapped[Wallet] = relationship(back_populates="participant", uselist=False)


class Wallet(IdMixin, TimestampMixin, Base):
    __tablename__ = "wallets"
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), unique=True
    )
    balance_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    participant: Mapped[Participant] = relationship(back_populates="wallet")
    event: Mapped[Event] = relationship()


class WalletAccessToken(IdMixin, Base):
    __tablename__ = "wallet_access_tokens"
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)


class Vendor(IdMixin, TimestampMixin, Base):
    __tablename__ = "vendors"
    __table_args__ = (UniqueConstraint("event_id", "pin_lookup"),)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    contract_number: Mapped[str | None] = mapped_column(String(255))
    pin_lookup: Mapped[str] = mapped_column(String(64))
    pin_hash: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)
    event: Mapped[Event] = relationship()


class VendorSession(IdMixin, Base):
    __tablename__ = "vendor_sessions"
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    last_activity_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    vendor: Mapped[Vendor] = relationship()


class VendorLoginAttempt(IdMixin, Base):
    __tablename__ = "vendor_login_attempts"
    ip_hash: Mapped[str] = mapped_column(String(64), index=True)
    successful: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class PaymentQrGrant(IdMixin, Base):
    __tablename__ = "payment_qr_grants"
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MoneyTransaction(IdMixin, TimestampMixin, Base):
    __tablename__ = "money_transactions"
    __table_args__ = (
        UniqueConstraint("event_id", "request_key"),
        Index("ix_money_wallet_status_created", "wallet_id", "status", "created_at"),
    )
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="RESTRICT"), index=True)
    wallet_id: Mapped[int] = mapped_column(
        ForeignKey("wallets.id", ondelete="RESTRICT"), index=True
    )
    vendor_id: Mapped[int | None] = mapped_column(
        ForeignKey("vendors.id", ondelete="SET NULL"), index=True
    )
    reference: Mapped[str] = mapped_column(String(40), unique=True)
    request_key: Mapped[str | None] = mapped_column(String(64))
    type: Mapped[TransactionType] = mapped_column(Enum(TransactionType, native_enum=False))
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus, native_enum=False), index=True
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    participant_code: Mapped[str] = mapped_column(String(100))
    participant_name: Mapped[str] = mapped_column(String(255))
    group_name: Mapped[str | None] = mapped_column(String(255))
    vendor_name: Mapped[str | None] = mapped_column(String(255))
    actor: Mapped[str] = mapped_column(String(255))
    decided_by: Mapped[str | None] = mapped_column(String(255))
    decision_at: Mapped[datetime | None] = mapped_column(DateTime)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    reversal_of_id: Mapped[int | None] = mapped_column(
        ForeignKey("money_transactions.id"), unique=True
    )
    note: Mapped[str | None] = mapped_column(String(500))


class CouponTemplate(IdMixin, TimestampMixin, Base):
    __tablename__ = "coupon_templates"
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    vendor_id: Mapped[int | None] = mapped_column(
        ForeignKey("vendors.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class CouponInstance(IdMixin, TimestampMixin, Base):
    __tablename__ = "coupon_instances"
    __table_args__ = (Index("ix_coupon_event_wallet_status", "event_id", "wallet_id", "status"),)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="RESTRICT"), index=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("coupon_templates.id", ondelete="RESTRICT"), index=True
    )
    wallet_id: Mapped[int] = mapped_column(
        ForeignKey("wallets.id", ondelete="RESTRICT"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[CouponStatus] = mapped_column(Enum(CouponStatus, native_enum=False), index=True)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime)
    redeemed_by_vendor_id: Mapped[int | None] = mapped_column(
        ForeignKey("vendors.id", ondelete="SET NULL")
    )
    wallet: Mapped[Wallet] = relationship()
    template: Mapped[CouponTemplate] = relationship()


class CouponAudit(IdMixin, Base):
    __tablename__ = "coupon_audits"
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="RESTRICT"), index=True)
    coupon_id: Mapped[int | None] = mapped_column(
        ForeignKey("coupon_instances.id", ondelete="SET NULL")
    )
    wallet_id: Mapped[int] = mapped_column(
        ForeignKey("wallets.id", ondelete="RESTRICT"), index=True
    )
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id", ondelete="SET NULL"))
    reference: Mapped[str] = mapped_column(String(40), unique=True)
    action: Mapped[str] = mapped_column(String(30), index=True)
    coupon_name: Mapped[str] = mapped_column(String(255))
    participant_code: Mapped[str] = mapped_column(String(100))
    participant_name: Mapped[str] = mapped_column(String(255))
    vendor_name: Mapped[str | None] = mapped_column(String(255))
    actor: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class EmailTemplate(IdMixin, TimestampMixin, Base):
    __tablename__ = "email_templates"
    __table_args__ = (
        UniqueConstraint("event_id", "name", "archived_at", name="uq_email_template_name"),
    )
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    document_json: Mapped[str] = mapped_column(Text().with_variant(mysql.MEDIUMTEXT(), "mysql"))
    rendered_html: Mapped[str] = mapped_column(Text().with_variant(mysql.MEDIUMTEXT(), "mysql"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    created_by: Mapped[str] = mapped_column(String(255))
    updated_by: Mapped[str] = mapped_column(String(255))
    archived_by: Mapped[str | None] = mapped_column(String(255))


class EmailAsset(IdMixin, Base):
    __tablename__ = "email_assets"
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), index=True
    )
    public_token: Mapped[str] = mapped_column(String(64), unique=True)
    original_name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(50))
    file_size: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    content: Mapped[bytes] = mapped_column(
        LargeBinary().with_variant(mysql.MEDIUMBLOB(), "mysql")
    )
    uploaded_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class EmailDelivery(IdMixin, Base):
    __tablename__ = "email_deliveries"
    __table_args__ = (
        Index("ix_email_delivery_event_created", "event_id", "created_at"),
    )
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="RESTRICT"), index=True
    )
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("email_templates.id", ondelete="SET NULL"), index=True
    )
    participant_id: Mapped[int | None] = mapped_column(
        ForeignKey("participants.id", ondelete="SET NULL"), index=True
    )
    recipient_email: Mapped[str] = mapped_column(String(320))
    recipient_name: Mapped[str | None] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    status: Mapped[EmailDeliveryStatus] = mapped_column(
        Enum(EmailDeliveryStatus, native_enum=False), index=True
    )
    error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)


class ScheduledAction(IdMixin, TimestampMixin, Base):
    __tablename__ = "scheduled_actions"
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    action_type: Mapped[ActionType] = mapped_column(Enum(ActionType, native_enum=False))
    email_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("email_templates.id", ondelete="SET NULL"), index=True
    )
    email_subject: Mapped[str | None] = mapped_column(String(255))
    email_html: Mapped[str | None] = mapped_column(
        Text().with_variant(mysql.MEDIUMTEXT(), "mysql")
    )
    schedule_type: Mapped[ScheduleType] = mapped_column(Enum(ScheduleType, native_enum=False))
    execute_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    schedule_start: Mapped[date | None] = mapped_column(Date)
    schedule_end: Mapped[date | None] = mapped_column(Date)
    schedule_time: Mapped[time | None] = mapped_column(Time)
    auto_delete: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_by: Mapped[str] = mapped_column(String(255))


class ActionWalletOverride(Base):
    __tablename__ = "action_wallet_overrides"
    action_id: Mapped[int] = mapped_column(
        ForeignKey("scheduled_actions.id", ondelete="CASCADE"), primary_key=True
    )
    wallet_id: Mapped[int] = mapped_column(
        ForeignKey("wallets.id", ondelete="CASCADE"), primary_key=True
    )
    included: Mapped[bool] = mapped_column(Boolean, default=True)


class ScheduledActionRun(IdMixin, Base):
    __tablename__ = "scheduled_action_runs"
    action_id: Mapped[int] = mapped_column(
        ForeignKey("scheduled_actions.id", ondelete="CASCADE"), index=True
    )
    run_key: Mapped[str] = mapped_column(String(100), unique=True)
    run_type: Mapped[str] = mapped_column(String(30))
    affected_count: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[bool] = mapped_column(Boolean)
    message: Mapped[str | None] = mapped_column(Text)
    executed_by: Mapped[str] = mapped_column(String(255))
    executed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
