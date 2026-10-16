"""Participant records and individual wallet access links."""

from typing import Literal

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..dependencies import require_admin, require_admin_csrf
from ..errors import ApiError
from ..models import (
    ActionWalletOverride,
    AdminUser,
    CouponAudit,
    CouponInstance,
    CouponStatus,
    MoneyTransaction,
    Participant,
    PaymentQrGrant,
    Wallet,
    WalletAccessToken,
)
from ..schemas import ParticipantCreate, ParticipantUpdate
from ..services import (
    create_participant_with_wallet,
    create_wallet_preview_token,
    event_supports,
    issue_coupons,
    reserved_minor,
    rotate_wallet_token,
)
from .admin_common import get_event

router = APIRouter()


# Participant search and record management.
@router.get("/events/{event_id}/participants")
def list_participants(
    event_id: int,
    search: str = "",
    group: str = "",
    wallet_status: Literal["active", "suspended"] | None = None,
    _: AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Return filtered participants, wallet availability, coupon counts, and event groups."""
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
    """Commit a participant, wallet, and eligible coupons; return the one-time wallet link."""
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
    """Commit editable participant details and return a confirmation message."""
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
    """Delete a participant and access records only when no protected audit history exists."""
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


# Secret wallet links: replacement links revoke old access; previews do not.
@router.post("/events/{event_id}/participants/{participant_id}/rotate-wallet-link")
def rotate_link(
    event_id: int,
    participant_id: int,
    _: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    """Commit revocation of previous wallet links and return the replacement secret URL."""
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
    """Commit a short-lived preview token and return its URL without rotating existing links."""
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
