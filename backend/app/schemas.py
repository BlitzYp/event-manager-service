from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .models import ActionType, EventMode, EventStatus, ScheduleType


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(ApiModel):
    message: str


class LoginRequest(ApiModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


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


class ParticipantCreate(ApiModel):
    participant_code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    group: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = None
    initial_balance_minor: int | None = Field(default=None, ge=0)


class ParticipantUpdate(ApiModel):
    name: str = Field(min_length=1, max_length=255)
    group: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = None


class VendorCreate(ApiModel):
    name: str = Field(min_length=1, max_length=255)
    pin: str = Field(pattern=r"^\d{6}$")


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


class CouponRedeem(ApiModel):
    token: str = Field(min_length=20, max_length=200)


class ActionCreate(ApiModel):
    name: str = Field(min_length=1, max_length=255)
    action_type: ActionType
    schedule_type: ScheduleType = ScheduleType.once
    execute_at: datetime
    schedule_end: datetime | None = None
    auto_delete: bool = False
    excluded_wallet_ids: list[int] = []


class ErrorBody(ApiModel):
    code: str
    message: str
    fields: list[dict[str, Any]] | None = None

