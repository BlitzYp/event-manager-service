from datetime import date, datetime, time
from typing import Any, Literal

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from .models import ActionType, EventMode, EventStatus, ScheduleType


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(ApiModel):
    message: str


def normalize_admin_email(value: str) -> str:
    try:
        return validate_email(
            value.strip(),
            check_deliverability=False,
            test_environment=True,
        ).normalized.lower()
    except EmailNotValidError as exc:
        raise ValueError(str(exc)) from exc


class LoginRequest(ApiModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=200)

    @field_validator("email")
    @classmethod
    def validate_admin_email(cls, value: str) -> str:
        return normalize_admin_email(value)


class AdminRegister(LoginRequest):
    password: str = Field(min_length=12, max_length=200)


class AdminAccountStatusUpdate(ApiModel):
    is_active: bool


class EventCreate(ApiModel):
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{2,50}$")
    name: str = Field(min_length=1, max_length=255)
    status: EventStatus = EventStatus.draft
    mode: EventMode
    currency: str = Field(default="EUR", pattern=r"^[A-Za-z]{3}$")
    default_balance_minor: int = Field(default=5000, ge=0)
    qr_ttl_seconds: int = Field(default=60, ge=15, le=600)
    approval_required: bool = True
    pending_payment_minutes: int = Field(default=5, ge=1, le=60)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class EventUpdate(EventCreate):
    pass


class EventApprovalUpdate(ApiModel):
    approval_required: bool


class ParticipantCreate(ApiModel):
    participant_code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    group: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = None
    initial_balance_minor: int | None = Field(default=None, ge=0)


class ParticipantUpdate(ApiModel):
    participant_code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    group: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = None


class VendorCreate(ApiModel):
    name: str = Field(min_length=1, max_length=255)
    pin: str = Field(pattern=r"^\d{6}$")
    contract_number: str | None = Field(default=None, max_length=255)


class VendorUpdate(ApiModel):
    name: str = Field(min_length=1, max_length=255)
    active: bool = True
    pin: str | None = Field(default=None, pattern=r"^\d{6}$")
    contract_number: str | None = Field(default=None, max_length=255)


class VendorLogin(ApiModel):
    event_code: str = Field(min_length=2, max_length=50)
    pin: str = Field(pattern=r"^\d{6}$")


class AdjustmentRequest(ApiModel):
    amount_minor: int = Field(gt=0)
    direction: str = Field(pattern=r"^(credit|debit)$")
    note: str = Field(min_length=1, max_length=500)


class PaymentCreate(ApiModel):
    qr_token: str | None = None
    participant_code: str | None = None
    wallet_id: int | None = None
    amount_minor: int = Field(gt=0)
    request_key: str = Field(min_length=8, max_length=64)


class DecisionRequest(ApiModel):
    decision: str = Field(pattern=r"^(approved|rejected)$")


class CouponTemplateCreate(ApiModel):
    name: str = Field(min_length=1, max_length=255)
    vendor_id: int | None = None
    sort_order: int = 0


class CouponTemplateUpdate(CouponTemplateCreate):
    active: bool = True
    apply_to_instances: bool = True


class CouponStatusUpdate(ApiModel):
    enabled: bool
    template_id: int | None = None


class CouponIssueRequest(ApiModel):
    template_ids: list[int] = Field(min_length=1, max_length=1_000)


class CouponRedeem(ApiModel):
    token: str | None = Field(default=None, min_length=20, max_length=200)
    code: str | None = Field(default=None, min_length=6, max_length=40)

    @model_validator(mode="after")
    def require_coupon_identifier(self) -> "CouponRedeem":
        if not self.token and not self.code:
            raise ValueError("A coupon token or coupon code is required.")
        return self


class EmailTemplateCreate(ApiModel):
    name: str = Field(min_length=1, max_length=255)
    subject: str = Field(min_length=1, max_length=255)
    document: dict[str, Any]
    rendered_html: str = Field(min_length=1, max_length=2_000_000)


class EmailTemplateUpdate(EmailTemplateCreate):
    version: int = Field(ge=1)


class EmailTemplateArchive(ApiModel):
    archived: bool


class EmailSendRequest(ApiModel):
    source: Literal["template", "basic"] = "template"
    template_id: int | None = None
    subject: str | None = Field(default=None, min_length=1, max_length=255)
    body: str | None = Field(default=None, max_length=100_000)
    participant_ids: list[int] = Field(default_factory=list, max_length=1_000)
    all_participants: bool = False
    group: str | None = Field(default=None, max_length=255)
    recipient_email: EmailStr | None = None
    recipient_name: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def require_one_recipient_scope(self) -> "EmailSendRequest":
        if self.source == "template":
            if self.template_id is None:
                raise ValueError("Choose an email template.")
            if self.body is not None:
                raise ValueError("Template emails cannot include a basic message body.")
        else:
            if self.template_id is not None:
                raise ValueError("Basic emails cannot include a template.")
            if not (self.subject or "").strip():
                raise ValueError("Basic emails require a subject.")
            if not (self.body or "").strip():
                raise ValueError("Basic emails require a message.")
        scopes = sum(
            [
                bool(self.participant_ids),
                self.all_participants,
                self.group is not None,
                self.recipient_email is not None,
            ]
        )
        if scopes != 1:
            raise ValueError(
                "Choose exactly one recipient scope: selected participants, all participants, "
                "a group, or one email address."
            )
        return self


class ActionCreate(ApiModel):
    name: str = Field(min_length=1, max_length=255)
    action_type: ActionType
    schedule_type: ScheduleType = ScheduleType.once
    execute_at: datetime
    schedule_start: date | None = None
    schedule_end: date | None = None
    schedule_time: time | None = None
    auto_delete: bool = False
    excluded_wallet_ids: list[int] = []
    email_template_id: int | None = None
    email_subject: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_daily_schedule(self) -> "ActionCreate":
        if self.schedule_type == ScheduleType.daily:
            if not self.schedule_start or not self.schedule_end or not self.schedule_time:
                raise ValueError(
                    "Daily schedules require start date, end date, and execution time."
                )
            if self.schedule_end < self.schedule_start:
                raise ValueError("Schedule end date cannot be before its start date.")
        if self.action_type == ActionType.send_email and not self.email_template_id:
            raise ValueError("Email actions require an email template.")
        if self.action_type != ActionType.send_email:
            self.email_template_id = None
            self.email_subject = None
        return self


class ActionWalletScope(ApiModel):
    operation: Literal["include", "exclude", "execute"]
    wallet_ids: list[int] = Field(min_length=1, max_length=10_000)


class ErrorBody(ApiModel):
    code: str
    message: str
    fields: list[dict[str, Any]] | None = None
