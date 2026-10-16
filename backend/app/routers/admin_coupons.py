"""Coupon templates, issuance, and individual or bulk availability."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..actions import record_coupon_audit
from ..database import get_db
from ..dependencies import require_admin, require_admin_csrf
from ..errors import ApiError
from ..models import (
    AdminUser,
    CouponInstance,
    CouponStatus,
    CouponTemplate,
    Participant,
    Vendor,
    Wallet,
)
from ..schemas import (
    CouponIssueRequest,
    CouponStatusUpdate,
    CouponTemplateCreate,
    CouponTemplateUpdate,
)
from ..security import coupon_code as make_coupon_code
from ..services import event_supports, issue_coupons
from .admin_common import get_event

router = APIRouter()


# Template configuration; issued coupons prevent destructive deletion.
@router.get("/events/{event_id}/coupon-templates")
def coupon_templates(
    event_id: int, _: AdminUser = Depends(require_admin), db: Session = Depends(get_db)
) -> dict:
    """Return event coupon templates in their configured display order."""
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
    """Commit an event coupon template after vendor validation; return its ID and name."""
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


@router.put("/events/{event_id}/coupon-templates/{template_id}")
def update_coupon_template(
    event_id: int,
    template_id: int,
    payload: CouponTemplateUpdate,
    admin: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    """Commit template edits and optional audited instance changes; return the changed count."""
    template = db.scalar(
        select(CouponTemplate)
        .where(CouponTemplate.id == template_id, CouponTemplate.event_id == event_id)
        .with_for_update()
    )
    if not template:
        raise ApiError(404, "not_found", "Coupon was not found.")
    if payload.vendor_id and not db.scalar(
        select(Vendor.id).where(Vendor.id == payload.vendor_id, Vendor.event_id == event_id)
    ):
        raise ApiError(422, "vendor_mismatch", "Vendor does not belong to this event.")
    template.name = payload.name
    template.vendor_id = payload.vendor_id
    template.sort_order = payload.sort_order
    template.active = payload.active
    changed = 0
    if payload.apply_to_instances:
        target = CouponStatus.available if payload.active else CouponStatus.disabled
        source = CouponStatus.disabled if payload.active else CouponStatus.available
        coupons = list(
            db.scalars(
                select(CouponInstance)
                .where(
                    CouponInstance.event_id == event_id,
                    CouponInstance.template_id == template_id,
                    CouponInstance.status == source,
                )
                .with_for_update()
            )
        )
        for coupon in coupons:
            coupon.status = target
            record_coupon_audit(db, coupon, target.value, f"admin:{admin.id}")
        changed = len(coupons)
    db.commit()
    return {
        "template": {
            "id": template.id,
            "name": template.name,
            "active": template.active,
        },
        "updated_instances": changed,
    }


@router.delete("/events/{event_id}/coupon-templates/{template_id}", status_code=204)
def delete_coupon_template(
    event_id: int,
    template_id: int,
    _: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> Response:
    """Delete and commit an unissued template; reject deletion once coupons exist."""
    template = db.scalar(
        select(CouponTemplate)
        .where(CouponTemplate.id == template_id, CouponTemplate.event_id == event_id)
        .with_for_update()
    )
    if not template:
        raise ApiError(404, "not_found", "Coupon was not found.")
    issued = db.scalar(
        select(func.count(CouponInstance.id)).where(CouponInstance.template_id == template.id)
    )
    if issued:
        raise ApiError(
            409,
            "coupon_has_history",
            "Issued coupons cannot be deleted; disable this coupon instead.",
        )
    db.delete(template)
    db.commit()
    return Response(status_code=204)


# Issued-coupon availability, listings, and audited status changes.
@router.patch("/events/{event_id}/coupons/status")
def set_coupon_status(
    event_id: int,
    payload: CouponStatusUpdate,
    admin: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    """Commit bulk coupon availability and matching template settings; return the instance count."""
    query = select(CouponInstance).where(
        CouponInstance.event_id == event_id,
        CouponInstance.status
        == (CouponStatus.disabled if payload.enabled else CouponStatus.available),
    )
    if payload.template_id is not None:
        query = query.where(CouponInstance.template_id == payload.template_id)
    coupons = list(db.scalars(query.with_for_update()))
    target = CouponStatus.available if payload.enabled else CouponStatus.disabled
    for coupon in coupons:
        coupon.status = target
        record_coupon_audit(db, coupon, target.value, f"admin:{admin.id}")
    templates_query = select(CouponTemplate).where(CouponTemplate.event_id == event_id)
    if payload.template_id is not None:
        templates_query = templates_query.where(CouponTemplate.id == payload.template_id)
    for template in db.scalars(templates_query):
        template.active = payload.enabled
    db.commit()
    return {"updated": len(coupons)}


@router.get("/events/{event_id}/coupon-instances")
def list_coupon_instances(
    event_id: int,
    _: AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Return up to 2,000 non-removed event coupons with participant and template details."""
    rows = db.execute(
        select(CouponInstance, CouponTemplate, Participant)
        .join(CouponTemplate, CouponTemplate.id == CouponInstance.template_id)
        .join(Wallet, Wallet.id == CouponInstance.wallet_id)
        .join(Participant, Participant.id == Wallet.participant_id)
        .where(
            CouponInstance.event_id == event_id,
            CouponInstance.status != CouponStatus.removed,
        )
        .order_by(Participant.name, CouponTemplate.sort_order)
        .limit(2_000)
    ).all()
    return {
        "coupons": [
            {
                "id": coupon.id,
                "code": make_coupon_code(coupon.id),
                "name": template.name,
                "participant_name": participant.name,
                "participant_code": participant.participant_code,
                "status": coupon.status,
            }
            for coupon, template, participant in rows
        ]
    }


@router.patch("/events/{event_id}/coupons/{coupon_id}/status")
def set_individual_coupon_status(
    event_id: int,
    coupon_id: int,
    payload: CouponStatusUpdate,
    admin: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    """Lock an unused coupon, commit an audited status change, and return its status."""
    coupon = db.scalar(
        select(CouponInstance)
        .where(
            CouponInstance.id == coupon_id,
            CouponInstance.event_id == event_id,
        )
        .with_for_update()
    )
    if not coupon:
        raise ApiError(404, "not_found", "Coupon was not found.")
    if coupon.status not in {CouponStatus.available, CouponStatus.disabled}:
        raise ApiError(409, "coupon_locked", "Redeemed coupons cannot be enabled or disabled.")
    target = CouponStatus.available if payload.enabled else CouponStatus.disabled
    if coupon.status != target:
        coupon.status = target
        record_coupon_audit(db, coupon, target.value, f"admin:{admin.id}")
        db.commit()
    return {"coupon": {"id": coupon.id, "status": coupon.status}}


@router.post("/events/{event_id}/coupons/issue")
def issue_event_coupons(
    event_id: int,
    payload: CouponIssueRequest,
    admin: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    """Commit issuance from selected active event templates and return the number issued."""
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
