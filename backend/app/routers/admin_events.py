"""Event creation, settings, and deletion for administrators."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db, utcnow
from ..dependencies import require_admin, require_admin_csrf
from ..errors import ApiError
from ..models import (
    AdminUser,
    CouponAudit,
    CouponInstance,
    EmailDelivery,
    Event,
    EventStatus,
    MoneyTransaction,
    Vendor,
    VendorSession,
)
from ..schemas import EventApprovalUpdate, EventCreate, EventUpdate
from .admin_common import event_json, get_event

router = APIRouter()


@router.get("/events")
def list_events(_: AdminUser = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    """Return events owned by the current administrator, or all events for a super-admin."""
    query = select(Event)
    if not _.is_super_admin:
        query = query.where(Event.admin_id == _.id)
    return {
        "events": [event_json(row) for row in db.scalars(query.order_by(Event.created_at.desc()))]
    }


@router.post("/events", status_code=201)
def create_event(
    payload: EventCreate,
    admin: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    """Commit a new owned event and return its public settings; reject duplicate codes."""
    event = Event(admin_id=admin.id, **payload.model_dump())
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
    """Commit event settings, revoke vendor sessions if inactive, and return the event."""
    event = get_event(db, event_id, lock=True)
    for key, value in payload.model_dump().items():
        setattr(event, key, value)
    if event.status != EventStatus.active:
        vendor_ids = select(Vendor.id).where(Vendor.event_id == event.id)
        for session in db.scalars(
            select(VendorSession).where(
                VendorSession.vendor_id.in_(vendor_ids),
                VendorSession.revoked_at.is_(None),
            )
        ):
            session.revoked_at = utcnow()
    db.commit()
    return {"event": event_json(event)}


@router.patch("/events/{event_id}/approval")
def update_event_approval(
    event_id: int,
    payload: EventApprovalUpdate,
    _: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    """Commit the payment-approval setting and return the refreshed event."""
    event = get_event(db, event_id, lock=True)
    event.approval_required = payload.approval_required
    db.commit()
    db.refresh(event)
    return {"event": event_json(event)}


@router.delete("/events/{event_id}", status_code=204)
def delete_event(
    event_id: int,
    _: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> Response:
    """Delete and commit an event only if it has no financial, coupon, or email history."""
    event = get_event(db, event_id, lock=True)
    transaction_count = db.scalar(
        select(func.count(MoneyTransaction.id)).where(MoneyTransaction.event_id == event_id)
    )
    coupon_audit_count = db.scalar(
        select(func.count(CouponAudit.id)).where(CouponAudit.event_id == event_id)
    )
    coupon_count = db.scalar(
        select(func.count(CouponInstance.id)).where(CouponInstance.event_id == event_id)
    )
    email_delivery_count = db.scalar(
        select(func.count(EmailDelivery.id)).where(EmailDelivery.event_id == event_id)
    )
    if transaction_count or coupon_audit_count or coupon_count or email_delivery_count:
        raise ApiError(
            409,
            "event_has_history",
            "Events with transaction, coupon, or email history cannot be deleted; "
            "archive it instead.",
        )
    db.delete(event)
    db.commit()
    return Response(status_code=204)
