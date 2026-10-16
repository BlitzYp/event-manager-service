"""Event vendors, PIN rotation, and session revocation."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..actions import record_coupon_audit
from ..database import get_db, utcnow
from ..dependencies import require_admin, require_admin_csrf
from ..errors import ApiError
from ..models import AdminUser, CouponInstance, CouponStatus, CouponTemplate, Vendor, VendorSession
from ..schemas import VendorCreate, VendorUpdate
from ..security import hash_password, keyed_lookup
from .admin_common import get_event

router = APIRouter()


# Vendor records and event-scoped availability.
@router.get("/events/{event_id}/vendors")
def list_vendors(
    event_id: int, _: AdminUser = Depends(require_admin), db: Session = Depends(get_db)
) -> dict:
    """Return vendor details and availability for the requested event, never PIN secrets."""
    get_event(db, event_id)
    rows = db.scalars(select(Vendor).where(Vendor.event_id == event_id).order_by(Vendor.name))
    return {
        "vendors": [
            {
                "id": v.id,
                "name": v.name,
                "contract_number": v.contract_number,
                "active": v.active,
                "last_login_at": v.last_login_at,
            }
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
    """Commit an event vendor with a hashed PIN and return its public details."""
    get_event(db, event_id)
    vendor = Vendor(
        event_id=event_id,
        name=payload.name,
        contract_number=payload.contract_number,
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


@router.put("/events/{event_id}/vendors/{vendor_id}")
def update_vendor(
    event_id: int,
    vendor_id: int,
    payload: VendorUpdate,
    _: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    """Commit vendor details and session revocations when disabled; return the vendor."""
    vendor = db.scalar(
        select(Vendor).where(Vendor.id == vendor_id, Vendor.event_id == event_id).with_for_update()
    )
    if not vendor:
        raise ApiError(404, "not_found", "Vendor was not found.")
    vendor.name = payload.name
    vendor.contract_number = payload.contract_number
    vendor.active = payload.active
    if payload.pin:
        vendor.pin_lookup = keyed_lookup(payload.pin, f"vendor-pin:{event_id}")
        vendor.pin_hash = hash_password(payload.pin)
    if payload.pin or not payload.active:
        for session in db.scalars(
            select(VendorSession).where(
                VendorSession.vendor_id == vendor.id, VendorSession.revoked_at.is_(None)
            )
        ):
            session.revoked_at = utcnow()
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "pin_in_use", "That PIN is already in use for this event.") from exc
    return {"vendor": {"id": vendor.id, "name": vendor.name, "active": vendor.active}}


@router.delete("/events/{event_id}/vendors/{vendor_id}", status_code=204)
def delete_vendor(
    event_id: int,
    vendor_id: int,
    admin: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> Response:
    """Delete an unused vendor or reject deletion when financial or coupon history exists."""
    vendor = db.scalar(
        select(Vendor).where(Vendor.id == vendor_id, Vendor.event_id == event_id).with_for_update()
    )
    if not vendor:
        raise ApiError(404, "not_found", "Vendor was not found.")
    templates = list(
        db.scalars(
            select(CouponTemplate).where(
                CouponTemplate.event_id == event_id,
                CouponTemplate.vendor_id == vendor.id,
            )
        )
    )
    template_ids = [template.id for template in templates]
    for template in templates:
        template.active = False
    if template_ids:
        coupons = list(
            db.scalars(
                select(CouponInstance)
                .where(
                    CouponInstance.event_id == event_id,
                    CouponInstance.template_id.in_(template_ids),
                    CouponInstance.status == CouponStatus.available,
                )
                .with_for_update()
            )
        )
        for coupon in coupons:
            coupon.status = CouponStatus.disabled
            record_coupon_audit(db, coupon, "disabled", f"admin:{admin.id}")
    db.delete(vendor)
    db.commit()
    return Response(status_code=204)


# Credential rotation always revokes existing sessions.
@router.put("/events/{event_id}/vendors/{vendor_id}/pin")
def rotate_vendor_pin(
    event_id: int,
    vendor_id: int,
    payload: VendorCreate,
    _: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    """Commit a new hashed PIN and revoke existing vendor sessions; return confirmation."""
    vendor = db.scalar(
        select(Vendor).where(Vendor.id == vendor_id, Vendor.event_id == event_id).with_for_update()
    )
    if not vendor:
        raise ApiError(404, "not_found", "Vendor was not found.")
    vendor.name = payload.name
    vendor.contract_number = payload.contract_number
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
