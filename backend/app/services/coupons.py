"""Coupon issuance and audit records; the caller commits the batch."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CouponAudit, CouponInstance, CouponStatus, CouponTemplate, Vendor, Wallet
from ..security import coupon_token, token_hash
from .common import reference


def issue_coupons(
    db: Session,
    event_id: int,
    wallet_ids: list[int] | None,
    actor: str,
    template_ids: list[int] | None = None,
) -> int:
    """Stage missing active-template coupons and issuance audits; return the number created.

    Existing available or disabled copies are not duplicated. The caller commits.
    """
    template_query = select(CouponTemplate).where(
        CouponTemplate.event_id == event_id, CouponTemplate.active.is_(True)
    )
    if template_ids is not None:
        template_query = template_query.where(CouponTemplate.id.in_(template_ids))
    templates = list(
        db.scalars(template_query)
    )
    vendor_names = {
        vendor.id: vendor.name
        for vendor in db.scalars(
            select(Vendor).where(
                Vendor.id.in_([template.vendor_id for template in templates if template.vendor_id])
            )
        )
    }
    wallet_query = select(Wallet).where(Wallet.event_id == event_id)
    if wallet_ids is not None:
        wallet_query = wallet_query.where(Wallet.id.in_(wallet_ids))
    wallets = list(db.scalars(wallet_query))
    issued = 0
    for wallet in wallets:
        for template in templates:
            exists = db.scalar(
                select(CouponInstance.id).where(
                    CouponInstance.wallet_id == wallet.id,
                    CouponInstance.template_id == template.id,
                    CouponInstance.status.in_([CouponStatus.available, CouponStatus.disabled]),
                )
            )
            if exists:
                continue
            coupon = CouponInstance(
                event_id=event_id,
                template_id=template.id,
                wallet_id=wallet.id,
                token_hash="pending",
                status=CouponStatus.available,
            )
            db.add(coupon)
            db.flush()
            coupon.token_hash = token_hash(coupon_token(coupon.id))
            db.add(
                CouponAudit(
                    event_id=event_id,
                    coupon_id=coupon.id,
                    wallet_id=wallet.id,
                    vendor_id=template.vendor_id,
                    reference=reference("CPI"),
                    action="issued",
                    coupon_name=template.name,
                    participant_code=wallet.participant.participant_code,
                    participant_name=wallet.participant.name,
                    vendor_name=(
                        vendor_names.get(template.vendor_id) if template.vendor_id else None
                    ),
                    actor=actor,
                )
            )
            issued += 1
    return issued
