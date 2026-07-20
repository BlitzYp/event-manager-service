import csv
import io
from datetime import date, datetime, time, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from openpyxl import Workbook
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..actions import execute_action
from ..config import settings
from ..database import get_db, utcnow
from ..dependencies import require_admin, require_admin_csrf
from ..errors import ApiError
from ..models import (
    ActionWalletOverride,
    AdminUser,
    CouponAudit,
    CouponInstance,
    CouponStatus,
    CouponTemplate,
    Event,
    MoneyTransaction,
    Participant,
    PaymentQrGrant,
    ScheduledAction,
    ScheduledActionRun,
    TransactionStatus,
    TransactionType,
    Vendor,
    VendorSession,
    Wallet,
    WalletAccessToken,
)
from ..schemas import (
    ActionCreate,
    ActionWalletScope,
    AdjustmentRequest,
    CouponIssueRequest,
    CouponTemplateCreate,
    EventCreate,
    EventUpdate,
    ParticipantCreate,
    ParticipantUpdate,
    VendorCreate,
)
from ..security import hash_password, keyed_lookup
from ..services import (
    create_participant_with_wallet,
    create_wallet_preview_token,
    event_supports,
    issue_coupons,
    reference,
    reserved_minor,
    rotate_wallet_token,
    validate_participant_csv,
)

router = APIRouter(prefix="/admin", tags=["administration"])


def event_json(row: Event) -> dict:
    return {
        "id": row.id,
        "code": row.code,
        "name": row.name,
        "status": row.status,
        "mode": row.mode,
        "currency": row.currency,
        "default_balance_minor": row.default_balance_minor,
        "qr_ttl_seconds": row.qr_ttl_seconds,
        "approval_required": row.approval_required,
        "pending_payment_minutes": row.pending_payment_minutes,
        "created_at": row.created_at,
    }


def get_event(db: Session, event_id: int, lock: bool = False) -> Event:
    query = select(Event).where(Event.id == event_id)
    if lock:
        query = query.with_for_update()
    event = db.scalar(query)
    if not event:
        raise ApiError(404, "not_found", "Event was not found.")
    return event


@router.get("/events")
def list_events(_: AdminUser = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    return {
        "events": [
            event_json(row) for row in db.scalars(select(Event).order_by(Event.created_at.desc()))
        ]
    }


@router.post("/events", status_code=201)
def create_event(
    payload: EventCreate, _: AdminUser = Depends(require_admin_csrf), db: Session = Depends(get_db)
) -> dict:
    event = Event(**payload.model_dump())
    db.add(event)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "event_code_exists", "An event with this code already exists.") from exc
    db.refresh(event)
    return {"event": event_json(event)}


@router.put("/events/{event_id}")
def update_event(
    event_id: int,
    payload: EventUpdate,
    _: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    event = get_event(db, event_id, lock=True)
    for key, value in payload.model_dump().items():
        setattr(event, key, value)
    db.commit()
    return {"event": event_json(event)}


@router.get("/events/{event_id}/participants")
def list_participants(
    event_id: int,
    search: str = "",
    group: str = "",
    wallet_status: Literal["active", "suspended"] | None = None,
    _: AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    event = get_event(db, event_id)
    query = select(Participant).join(Wallet).where(Participant.event_id == event_id)
    if search:
        term = f"%{search}%"
        query = query.where(
            or_(
                Participant.name.like(term),
                Participant.participant_code.like(term),
                Participant.group_name.like(term),
            )
        )
    if group:
        query = query.where(Participant.group_name == group)
    if wallet_status:
        query = query.where(Wallet.enabled.is_(wallet_status == "active"))
    rows = list(db.scalars(query.order_by(Participant.name)))
    groups = list(
        db.scalars(
            select(Participant.group_name)
            .where(Participant.event_id == event_id, Participant.group_name.is_not(None))
            .distinct()
            .order_by(Participant.group_name)
        )
    )
    coupon_counts: dict[int, dict[str, int]] = {}
    if event_supports(event, "coupons"):
        for wallet_id, status, count in db.execute(
            select(CouponInstance.wallet_id, CouponInstance.status, func.count(CouponInstance.id))
            .where(
                CouponInstance.event_id == event_id,
                CouponInstance.status != CouponStatus.removed,
            )
            .group_by(CouponInstance.wallet_id, CouponInstance.status)
        ):
            summary = coupon_counts.setdefault(
                wallet_id, {"available": 0, "disabled": 0, "redeemed": 0, "total": 0}
            )
            summary[status.value] = count
            summary["total"] += count
    return {
        "groups": groups,
        "participants": [
            {
                "id": p.id,
                "participant_code": p.participant_code,
                "name": p.name,
                "group": p.group_name,
                "email": p.email,
                "wallet": {
                    "id": p.wallet.id,
                    "balance_minor": p.wallet.balance_minor,
                    "enabled": p.wallet.enabled,
                    "reserved_minor": reserved_minor(db, p.wallet.id),
                },
                "coupons": coupon_counts.get(
                    p.wallet.id,
                    {"available": 0, "disabled": 0, "redeemed": 0, "total": 0},
                ),
            }
            for p in rows
        ],
    }


@router.post("/events/{event_id}/participants", status_code=201)
def create_participant(
    event_id: int,
    payload: ParticipantCreate,
    admin: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    event = get_event(db, event_id)
    try:
        participant, wallet, raw_token = create_participant_with_wallet(
            db,
            event,
            payload.participant_code,
            payload.name,
            payload.group,
            str(payload.email) if payload.email else None,
            payload.initial_balance_minor,
        )
        if event_supports(event, "coupons"):
            issue_coupons(db, event.id, [wallet.id], f"admin:{admin.id}")
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(
            409, "participant_code_exists", "Participant code already exists in this event."
        ) from exc
    return {
        "participant": {
            "id": participant.id,
            "participant_code": participant.participant_code,
            "name": participant.name,
        },
        "wallet_link": f"{settings.public_app_url}/wallet/{raw_token}",
        "notice": "This wallet link is shown once. Store or distribute it now.",
    }


@router.put("/events/{event_id}/participants/{participant_id}")
def update_participant(
    event_id: int,
    participant_id: int,
    payload: ParticipantUpdate,
    _: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    participant = db.scalar(
        select(Participant)
        .where(Participant.id == participant_id, Participant.event_id == event_id)
        .with_for_update()
    )
    if not participant:
        raise ApiError(404, "not_found", "Participant was not found.")
    participant.participant_code = payload.participant_code
    participant.name = payload.name
    participant.group_name = payload.group
    participant.email = str(payload.email) if payload.email else None
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(
            409,
            "participant_code_exists",
            "Participant code already exists in this event.",
        ) from exc
    return {"message": "Participant updated."}


@router.delete("/events/{event_id}/participants/{participant_id}", status_code=204)
def delete_participant(
    event_id: int,
    participant_id: int,
    _: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> Response:
    participant = db.scalar(
        select(Participant)
        .where(Participant.id == participant_id, Participant.event_id == event_id)
        .with_for_update()
    )
    if not participant:
        raise ApiError(404, "not_found", "Participant was not found.")
    wallet = participant.wallet
    money_history = db.scalar(
        select(func.count(MoneyTransaction.id)).where(MoneyTransaction.wallet_id == wallet.id)
    )
    coupon_history = db.scalar(
        select(func.count(CouponAudit.id)).where(CouponAudit.wallet_id == wallet.id)
    )
    if money_history or coupon_history:
        raise ApiError(
            409,
            "participant_has_history",
            "Participants with financial or coupon history cannot be deleted. "
            "Suspend the wallet instead.",
        )
    db.query(ActionWalletOverride).filter(ActionWalletOverride.wallet_id == wallet.id).delete(
        synchronize_session=False
    )
    db.query(PaymentQrGrant).filter(PaymentQrGrant.wallet_id == wallet.id).delete(
        synchronize_session=False
    )
    db.query(WalletAccessToken).filter(WalletAccessToken.wallet_id == wallet.id).delete(
        synchronize_session=False
    )
    db.query(CouponInstance).filter(CouponInstance.wallet_id == wallet.id).delete(
        synchronize_session=False
    )
    db.delete(wallet)
    db.flush()
    db.delete(participant)
    db.commit()
    return Response(status_code=204)


@router.post("/events/{event_id}/participants/{participant_id}/rotate-wallet-link")
def rotate_link(
    event_id: int,
    participant_id: int,
    _: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    wallet = db.scalar(
        select(Wallet)
        .join(Participant)
        .where(Participant.id == participant_id, Wallet.event_id == event_id)
        .with_for_update()
    )
    if not wallet:
        raise ApiError(404, "not_found", "Participant was not found.")
    raw = rotate_wallet_token(db, wallet)
    db.commit()
    return {
        "wallet_link": f"{settings.public_app_url}/wallet/{raw}",
        "notice": "This replacement link is shown once.",
    }


@router.post("/events/{event_id}/participants/{participant_id}/wallet-preview")
def create_wallet_preview(
    event_id: int,
    participant_id: int,
    _: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    wallet = db.scalar(
        select(Wallet)
        .join(Participant)
        .where(Participant.id == participant_id, Wallet.event_id == event_id)
    )
    if not wallet:
        raise ApiError(404, "not_found", "Participant was not found.")
    raw, expires_at = create_wallet_preview_token(db, wallet)
    db.commit()
    return {
        "wallet_link": f"{settings.public_app_url}/wallet/{raw}",
        "expires_at": expires_at,
        "notice": (
            "This admin preview link is short-lived and does not replace the participant link."
        ),
    }


@router.post("/events/{event_id}/participants/import")
async def import_participants(
    event_id: int,
    file: UploadFile = File(...),
    admin: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> Response:
    event = get_event(db, event_id)
    content = await file.read()
    if len(content) > 5_000_000:
        raise ApiError(413, "file_too_large", "CSV file is too large.")
    rows = validate_participant_csv(content)
    codes = [str(row["participant_code"]) for row in rows]
    existing = set(
        db.scalars(
            select(Participant.participant_code).where(
                Participant.event_id == event_id, Participant.participant_code.in_(codes)
            )
        )
    )
    if existing:
        raise ApiError(
            409,
            "participant_code_exists",
            f"Codes already exist: {', '.join(sorted(existing)[:20])}",
        )
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["participant_code", "name", "group", "email", "wallet_link"])
    try:
        for row in rows:
            participant, wallet, raw = create_participant_with_wallet(
                db,
                event,
                str(row["participant_code"]),
                str(row["name"]),
                str(row["group"]) if row["group"] else None,
                str(row["email"]) if row["email"] else None,
            )
            if event_supports(event, "coupons"):
                issue_coupons(db, event.id, [wallet.id], f"admin:{admin.id}")
            writer.writerow(
                [
                    participant.participant_code,
                    participant.name,
                    participant.group_name or "",
                    participant.email or "",
                    f"{settings.public_app_url}/wallet/{raw}",
                ]
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return Response(
        output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{event.code}-wallet-links.csv"',
            "Cache-Control": "no-store",
        },
    )


@router.patch("/events/{event_id}/wallets/{wallet_id}/enabled")
def set_wallet_enabled(
    event_id: int,
    wallet_id: int,
    enabled: bool,
    _: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    wallet = db.scalar(
        select(Wallet).where(Wallet.id == wallet_id, Wallet.event_id == event_id).with_for_update()
    )
    if not wallet:
        raise ApiError(404, "not_found", "Wallet was not found.")
    wallet.enabled = enabled
    db.commit()
    return {"message": "Wallet updated."}


@router.post("/events/{event_id}/wallets/{wallet_id}/adjust")
def adjust_wallet(
    event_id: int,
    wallet_id: int,
    payload: AdjustmentRequest,
    admin: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    wallet = db.scalar(
        select(Wallet).where(Wallet.id == wallet_id, Wallet.event_id == event_id).with_for_update()
    )
    if not wallet:
        raise ApiError(404, "not_found", "Wallet was not found.")
    if not event_supports(wallet.event, "money"):
        raise ApiError(409, "money_not_enabled", "Money is not enabled for this event.")
    if (
        payload.direction == "debit"
        and payload.amount_minor > wallet.balance_minor - reserved_minor(db, wallet.id)
    ):
        raise ApiError(409, "insufficient_funds", "Wallet has insufficient available funds.")
    wallet.balance_minor += (
        payload.amount_minor if payload.direction == "credit" else -payload.amount_minor
    )
    participant = wallet.participant
    row = MoneyTransaction(
        event_id=event_id,
        wallet_id=wallet.id,
        reference=reference("ADJ"),
        type=TransactionType.admin_credit
        if payload.direction == "credit"
        else TransactionType.admin_debit,
        status=TransactionStatus.approved,
        amount_minor=payload.amount_minor,
        participant_code=participant.participant_code,
        participant_name=participant.name,
        group_name=participant.group_name,
        actor=f"admin:{admin.id}",
        decided_by=f"admin:{admin.id}",
        decision_at=utcnow(),
        note=payload.note,
    )
    db.add(row)
    db.commit()
    return {
        "transaction": {"id": row.id, "reference": row.reference},
        "balance_minor": wallet.balance_minor,
    }


@router.post("/events/{event_id}/transactions/{transaction_id}/reverse")
def reverse_transaction(
    event_id: int,
    transaction_id: int,
    note: str = Query(min_length=1, max_length=500),
    admin: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    original = db.scalar(
        select(MoneyTransaction)
        .where(
            MoneyTransaction.id == transaction_id,
            MoneyTransaction.event_id == event_id,
            MoneyTransaction.type == TransactionType.vendor_debit,
            MoneyTransaction.status == TransactionStatus.approved,
        )
        .with_for_update()
    )
    if not original:
        raise ApiError(409, "not_reversible", "Transaction cannot be reversed.")
    if db.scalar(select(MoneyTransaction.id).where(MoneyTransaction.reversal_of_id == original.id)):
        raise ApiError(409, "already_reversed", "Transaction has already been reversed.")
    wallet = db.scalar(select(Wallet).where(Wallet.id == original.wallet_id).with_for_update())
    if not wallet:
        raise ApiError(409, "wallet_unavailable", "Wallet is unavailable.")
    wallet.balance_minor += original.amount_minor
    original.status = TransactionStatus.reversed
    reversal = MoneyTransaction(
        event_id=event_id,
        wallet_id=wallet.id,
        vendor_id=original.vendor_id,
        reference=reference("REV"),
        type=TransactionType.reversal,
        status=TransactionStatus.approved,
        amount_minor=original.amount_minor,
        participant_code=original.participant_code,
        participant_name=original.participant_name,
        group_name=original.group_name,
        vendor_name=original.vendor_name,
        actor=f"admin:{admin.id}",
        decided_by=f"admin:{admin.id}",
        decision_at=utcnow(),
        reversal_of_id=original.id,
        note=note,
    )
    db.add(reversal)
    db.commit()
    return {"transaction": {"id": reversal.id, "reference": reversal.reference}}


@router.get("/events/{event_id}/vendors")
def list_vendors(
    event_id: int, _: AdminUser = Depends(require_admin), db: Session = Depends(get_db)
) -> dict:
    get_event(db, event_id)
    rows = db.scalars(select(Vendor).where(Vendor.event_id == event_id).order_by(Vendor.name))
    return {
        "vendors": [
            {"id": v.id, "name": v.name, "active": v.active, "last_login_at": v.last_login_at}
            for v in rows
        ]
    }


@router.post("/events/{event_id}/vendors", status_code=201)
def create_vendor(
    event_id: int,
    payload: VendorCreate,
    _: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    get_event(db, event_id)
    vendor = Vendor(
        event_id=event_id,
        name=payload.name,
        pin_lookup=keyed_lookup(payload.pin, f"vendor-pin:{event_id}"),
        pin_hash=hash_password(payload.pin),
    )
    db.add(vendor)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "pin_in_use", "That PIN is already in use for this event.") from exc
    return {"vendor": {"id": vendor.id, "name": vendor.name, "active": vendor.active}}


@router.put("/events/{event_id}/vendors/{vendor_id}/pin")
def rotate_vendor_pin(
    event_id: int,
    vendor_id: int,
    payload: VendorCreate,
    _: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    vendor = db.scalar(
        select(Vendor).where(Vendor.id == vendor_id, Vendor.event_id == event_id).with_for_update()
    )
    if not vendor:
        raise ApiError(404, "not_found", "Vendor was not found.")
    vendor.name = payload.name
    vendor.pin_lookup = keyed_lookup(payload.pin, f"vendor-pin:{event_id}")
    vendor.pin_hash = hash_password(payload.pin)
    db.execute(select(VendorSession).where(VendorSession.vendor_id == vendor.id).with_for_update())
    for session in db.scalars(
        select(VendorSession).where(
            VendorSession.vendor_id == vendor.id, VendorSession.revoked_at.is_(None)
        )
    ):
        session.revoked_at = utcnow()
    db.commit()
    return {"message": "Vendor PIN rotated and active sessions revoked."}


@router.get("/events/{event_id}/coupon-templates")
def coupon_templates(
    event_id: int, _: AdminUser = Depends(require_admin), db: Session = Depends(get_db)
) -> dict:
    get_event(db, event_id)
    rows = db.scalars(
        select(CouponTemplate)
        .where(CouponTemplate.event_id == event_id)
        .order_by(CouponTemplate.sort_order, CouponTemplate.name)
    )
    return {
        "templates": [
            {
                "id": t.id,
                "name": t.name,
                "vendor_id": t.vendor_id,
                "sort_order": t.sort_order,
                "active": t.active,
            }
            for t in rows
        ]
    }


@router.post("/events/{event_id}/coupon-templates", status_code=201)
def create_coupon_template(
    event_id: int,
    payload: CouponTemplateCreate,
    _: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    event = get_event(db, event_id)
    if not event_supports(event, "coupons"):
        raise ApiError(409, "coupons_not_enabled", "Coupons are not enabled for this event.")
    if payload.vendor_id and not db.scalar(
        select(Vendor.id).where(Vendor.id == payload.vendor_id, Vendor.event_id == event_id)
    ):
        raise ApiError(422, "vendor_mismatch", "Vendor does not belong to this event.")
    template = CouponTemplate(event_id=event_id, **payload.model_dump())
    db.add(template)
    db.commit()
    return {"template": {"id": template.id, "name": template.name}}


@router.post("/events/{event_id}/coupons/issue")
def issue_event_coupons(
    event_id: int,
    payload: CouponIssueRequest,
    admin: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    event = get_event(db, event_id)
    if not event_supports(event, "coupons"):
        raise ApiError(409, "coupons_not_enabled", "Coupons are not enabled for this event.")
    template_count = db.scalar(
        select(func.count(CouponTemplate.id)).where(
            CouponTemplate.event_id == event_id,
            CouponTemplate.id.in_(payload.template_ids),
            CouponTemplate.active.is_(True),
        )
    )
    if template_count != len(set(payload.template_ids)):
        raise ApiError(422, "invalid_coupon_templates", "Select active coupons from this event.")
    count = issue_coupons(
        db,
        event_id,
        None,
        f"admin:{admin.id}",
        template_ids=payload.template_ids,
    )
    db.commit()
    return {"issued": count}


@router.get("/events/{event_id}/transactions")
def transactions(
    event_id: int,
    status: TransactionStatus | None = None,
    transaction_type: TransactionType | None = Query(default=None, alias="type"),
    vendor_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str = "",
    _: AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    get_event(db, event_id)
    query = transaction_query(
        event_id,
        status=status,
        transaction_type=transaction_type,
        vendor_id=vendor_id,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )
    rows = db.scalars(query.order_by(MoneyTransaction.created_at.desc()).limit(500))
    return {
        "transactions": [
            {
                "id": r.id,
                "reference": r.reference,
                "type": r.type,
                "status": r.status,
                "amount_minor": r.amount_minor,
                "participant_code": r.participant_code,
                "participant_name": r.participant_name,
                "group": r.group_name,
                "vendor_id": r.vendor_id,
                "vendor_name": r.vendor_name,
                "created_at": r.created_at,
            }
            for r in rows
        ]
    }


def transaction_query(
    event_id: int,
    *,
    status: TransactionStatus | None = None,
    transaction_type: TransactionType | None = None,
    vendor_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str = "",
):
    query = select(MoneyTransaction).where(MoneyTransaction.event_id == event_id)
    if status:
        query = query.where(MoneyTransaction.status == status)
    if transaction_type:
        query = query.where(MoneyTransaction.type == transaction_type)
    if vendor_id:
        query = query.where(MoneyTransaction.vendor_id == vendor_id)
    if date_from:
        query = query.where(MoneyTransaction.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        query = query.where(
            MoneyTransaction.created_at < datetime.combine(date_to + timedelta(days=1), time.min)
        )
    if search:
        term = f"%{search}%"
        query = query.where(
            or_(
                MoneyTransaction.participant_name.like(term),
                MoneyTransaction.participant_code.like(term),
                MoneyTransaction.group_name.like(term),
                MoneyTransaction.reference.like(term),
                MoneyTransaction.vendor_name.like(term),
            )
        )
    return query


@router.get("/events/{event_id}/coupon-audits")
def coupon_audits(
    event_id: int,
    vendor_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str = "",
    _: AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    get_event(db, event_id)
    query = select(CouponAudit).where(CouponAudit.event_id == event_id)
    if vendor_id:
        query = query.where(CouponAudit.vendor_id == vendor_id)
    if date_from:
        query = query.where(CouponAudit.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        query = query.where(
            CouponAudit.created_at < datetime.combine(date_to + timedelta(days=1), time.min)
        )
    if search:
        term = f"%{search}%"
        query = query.where(
            or_(
                CouponAudit.participant_name.like(term),
                CouponAudit.participant_code.like(term),
                CouponAudit.reference.like(term),
                CouponAudit.coupon_name.like(term),
                CouponAudit.vendor_name.like(term),
            )
        )
    rows = db.scalars(query.order_by(CouponAudit.created_at.desc()).limit(500))
    return {
        "audits": [
            {
                "id": r.id,
                "reference": r.reference,
                "action": r.action,
                "coupon_name": r.coupon_name,
                "participant_code": r.participant_code,
                "participant_name": r.participant_name,
                "vendor_id": r.vendor_id,
                "vendor_name": r.vendor_name,
                "actor": r.actor,
                "created_at": r.created_at,
            }
            for r in rows
        ]
    }


def ledger_rows(
    db: Session,
    event_id: int,
    *,
    status: TransactionStatus | None = None,
    transaction_type: TransactionType | None = None,
    vendor_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str = "",
) -> list[list]:
    rows = db.scalars(
        transaction_query(
            event_id,
            status=status,
            transaction_type=transaction_type,
            vendor_id=vendor_id,
            date_from=date_from,
            date_to=date_to,
            search=search,
        ).order_by(MoneyTransaction.created_at.desc())
    )
    return [
        [
            r.reference,
            r.created_at.isoformat(),
            r.type.value,
            r.status.value,
            r.amount_minor,
            r.participant_code,
            r.participant_name,
            r.group_name or "",
            r.vendor_name or "",
            r.actor,
            r.note or "",
        ]
        for r in rows
    ]


@router.get("/events/{event_id}/transactions/export.{format}")
def export_transactions(
    event_id: int,
    format: str,
    status: TransactionStatus | None = None,
    transaction_type: TransactionType | None = Query(default=None, alias="type"),
    vendor_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str = "",
    _: AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    event = get_event(db, event_id)
    if format not in {"csv", "xlsx"}:
        raise ApiError(404, "not_found", "Export format was not found.")
    headers = [
        "reference",
        "created_at",
        "type",
        "status",
        "amount_minor",
        "participant_code",
        "participant_name",
        "group",
        "vendor",
        "actor",
        "note",
    ]
    rows = ledger_rows(
        db,
        event_id,
        status=status,
        transaction_type=transaction_type,
        vendor_id=vendor_id,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )
    if format == "csv":
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        return Response(
            output.getvalue(),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{event.code}-transactions.csv"'
            },
        )
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Transactions"
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    binary = io.BytesIO()
    workbook.save(binary)
    return Response(
        binary.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{event.code}-transactions.xlsx"'},
    )


@router.get("/events/{event_id}/actions")
def list_actions(
    event_id: int, _: AdminUser = Depends(require_admin), db: Session = Depends(get_db)
) -> dict:
    get_event(db, event_id)
    actions = list(
        db.scalars(
            select(ScheduledAction)
            .where(ScheduledAction.event_id == event_id)
            .order_by(ScheduledAction.execute_at.desc())
        )
    )
    runs = list(
        db.scalars(
            select(ScheduledActionRun)
            .join(ScheduledAction)
            .where(ScheduledAction.event_id == event_id)
            .order_by(ScheduledActionRun.executed_at.desc())
            .limit(50)
        )
    )
    return {
        "actions": [
            {
                "id": a.id,
                "name": a.name,
                "action_type": a.action_type,
                "schedule_type": a.schedule_type,
                "execute_at": a.execute_at,
                "schedule_start": a.schedule_start,
                "schedule_end": a.schedule_end,
                "schedule_time": a.schedule_time,
                "enabled": a.enabled,
                "completed_at": a.completed_at,
            }
            for a in actions
        ],
        "runs": [
            {
                "id": r.id,
                "action_id": r.action_id,
                "success": r.success,
                "affected_count": r.affected_count,
                "message": r.message,
                "executed_at": r.executed_at,
            }
            for r in runs
        ],
    }


@router.post("/events/{event_id}/actions", status_code=201)
def create_action(
    event_id: int,
    payload: ActionCreate,
    admin: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    get_event(db, event_id)
    action = ScheduledAction(
        event_id=event_id,
        name=payload.name,
        action_type=payload.action_type,
        schedule_type=payload.schedule_type,
        execute_at=payload.execute_at,
        schedule_start=payload.schedule_start or payload.execute_at.date(),
        schedule_end=payload.schedule_end,
        schedule_time=payload.schedule_time or payload.execute_at.time().replace(tzinfo=None),
        auto_delete=payload.auto_delete,
        created_by=f"admin:{admin.id}",
    )
    db.add(action)
    db.flush()
    for wallet_id in payload.excluded_wallet_ids:
        belongs = db.scalar(
            select(Wallet.id).where(Wallet.id == wallet_id, Wallet.event_id == event_id)
        )
        if belongs:
            db.add(ActionWalletOverride(action_id=action.id, wallet_id=wallet_id, included=False))
    db.commit()
    return {"action": {"id": action.id, "name": action.name}}


@router.post("/events/{event_id}/actions/{action_id}/run")
def run_action_now(
    event_id: int,
    action_id: int,
    admin: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    action = db.scalar(
        select(ScheduledAction)
        .where(ScheduledAction.id == action_id, ScheduledAction.event_id == event_id)
        .with_for_update()
    )
    if not action:
        raise ApiError(404, "not_found", "Scheduled action was not found.")
    # Manual runs are independently keyed and never consume the configured schedule.
    run = execute_action(
        db,
        action,
        f"manual-{utcnow().strftime('%Y%m%d%H%M%S%f')}",
        f"admin:{admin.id}",
        advance_schedule=False,
    )
    return {
        "run": {
            "id": run.id,
            "success": run.success,
            "affected_count": run.affected_count,
            "message": run.message,
        }
    }


@router.post("/events/{event_id}/actions/{action_id}/wallet-scope")
def apply_action_wallet_scope(
    event_id: int,
    action_id: int,
    payload: ActionWalletScope,
    admin: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    action = db.scalar(
        select(ScheduledAction)
        .where(ScheduledAction.id == action_id, ScheduledAction.event_id == event_id)
        .with_for_update()
    )
    if not action:
        raise ApiError(404, "not_found", "Scheduled action was not found.")

    requested_ids = list(dict.fromkeys(payload.wallet_ids))
    event_wallet_ids = set(
        db.scalars(
            select(Wallet.id).where(
                Wallet.event_id == event_id,
                Wallet.id.in_(requested_ids),
            )
        )
    )
    if len(event_wallet_ids) != len(requested_ids):
        raise ApiError(
            400,
            "invalid_wallet_scope",
            "One or more selected wallets do not belong to this event.",
        )

    if payload.operation == "execute":
        run = execute_action(
            db,
            action,
            f"scope-{utcnow().strftime('%Y%m%d%H%M%S%f')}",
            f"admin:{admin.id}",
            advance_schedule=False,
            wallet_ids_override=requested_ids,
        )
        return {
            "message": run.message,
            "affected_count": run.affected_count,
            "run_id": run.id,
        }

    included = payload.operation == "include"
    for wallet_id in requested_ids:
        override = db.get(ActionWalletOverride, (action.id, wallet_id))
        if override:
            override.included = included
        else:
            db.add(
                ActionWalletOverride(
                    action_id=action.id,
                    wallet_id=wallet_id,
                    included=included,
                )
            )
    db.commit()
    operation = "included in" if included else "excluded from"
    return {
        "message": f"{len(requested_ids)} wallets were {operation} the schedule.",
        "affected_count": len(requested_ids),
    }
