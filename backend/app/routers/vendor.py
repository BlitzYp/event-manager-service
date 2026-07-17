from datetime import timedelta

from fastapi import APIRouter, Cookie, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db, utcnow
from ..dependencies import require_vendor, require_vendor_csrf
from ..errors import ApiError
from ..models import (
    CouponAudit,
    CouponInstance,
    CouponStatus,
    CouponTemplate,
    Event,
    EventStatus,
    MoneyTransaction,
    Vendor,
    VendorLoginAttempt,
    VendorSession,
    Wallet,
)
from ..schemas import CouponRedeem, PaymentCreate, VendorLogin
from ..security import (
    coupon_id_from_token,
    keyed_lookup,
    new_token,
    token_hash,
    verify_password,
)
from ..services import create_vendor_payment, reference, reserved_minor, resolve_payment_target

router = APIRouter(prefix="/vendor", tags=["vendor-wallet"])


@router.post("/login")
def login(payload: VendorLogin, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    ip_hash = keyed_lookup(request.client.host if request.client else "unknown", "vendor-ip")
    attempts = db.scalar(
        select(func.count(VendorLoginAttempt.id)).where(
            VendorLoginAttempt.ip_hash == ip_hash,
            VendorLoginAttempt.successful.is_(False),
            VendorLoginAttempt.created_at > utcnow() - timedelta(minutes=15),
        )
    )
    if int(attempts or 0) >= 10:
        raise ApiError(429, "login_limited", "Too many attempts. Try again later.")
    event = db.scalar(select(Event).where(Event.code == payload.event_code.lower(), Event.status == EventStatus.active))
    vendor = None
    if event:
        vendor = db.scalar(
            select(Vendor).where(
                Vendor.event_id == event.id,
                Vendor.pin_lookup == keyed_lookup(payload.pin, f"vendor-pin:{event.id}"),
                Vendor.active.is_(True),
            )
        )
    success = bool(vendor and verify_password(payload.pin, vendor.pin_hash))
    db.add(VendorLoginAttempt(ip_hash=ip_hash, successful=success))
    if not success or not vendor:
        db.commit()
        raise ApiError(401, "invalid_credentials", "Event code or PIN is incorrect.")
    raw_session, raw_csrf = new_token(), new_token()
    db.add(
        VendorSession(
            vendor_id=vendor.id, token_hash=token_hash(raw_session), csrf_hash=token_hash(raw_csrf)
        )
    )
    vendor.last_login_at = utcnow()
    db.commit()
    response.set_cookie(
        "vendor_session", raw_session, httponly=True, secure=settings.cookie_secure,
        samesite="lax", max_age=settings.vendor_session_idle_minutes * 60, path="/",
    )
    return {
        "vendor": {"id": vendor.id, "name": vendor.name, "event_id": vendor.event_id, "event_name": vendor.event.name},
        "csrf_token": raw_csrf,
    }


@router.get("/me")
def me(vendor: Vendor = Depends(require_vendor)) -> dict:
    return {"vendor": {"id": vendor.id, "name": vendor.name, "event_id": vendor.event_id, "event_name": vendor.event.name}}


@router.post("/csrf")
def csrf(
    vendor: Vendor = Depends(require_vendor), db: Session = Depends(get_db),
    vendor_session: str | None = Cookie(default=None),
) -> dict:
    row = db.scalar(select(VendorSession).where(VendorSession.token_hash == token_hash(vendor_session or "")))
    if not row:
        raise ApiError(401, "authentication_required", "Authentication required.")
    raw = new_token()
    row.csrf_hash = token_hash(raw)
    db.commit()
    return {"csrf_token": raw}


@router.post("/logout")
def logout(
    response: Response, vendor: Vendor = Depends(require_vendor_csrf), db: Session = Depends(get_db),
    vendor_session: str | None = Cookie(default=None),
) -> dict:
    row = db.scalar(select(VendorSession).where(VendorSession.token_hash == token_hash(vendor_session or "")))
    if row:
        row.revoked_at = utcnow()
        db.commit()
    response.delete_cookie("vendor_session", path="/")
    return {"message": "Signed out."}


@router.get("/lookup")
def lookup(
    qr_token: str | None = None, participant_code: str | None = None,
    vendor: Vendor = Depends(require_vendor), db: Session = Depends(get_db),
) -> dict:
    coupon_id = coupon_id_from_token(qr_token or "")
    if coupon_id:
        coupon = db.scalar(select(CouponInstance).where(CouponInstance.id == coupon_id, CouponInstance.event_id == vendor.event_id))
        if not coupon:
            raise ApiError(404, "item_unavailable", "QR code is invalid or unavailable.")
        template = db.get(CouponTemplate, coupon.template_id)
        if not template or (template.vendor_id and template.vendor_id != vendor.id):
            raise ApiError(404, "item_unavailable", "QR code is invalid or unavailable.")
        return {"kind": "coupon", "coupon": {"token": qr_token, "name": template.name, "status": coupon.status, "participant_name": coupon.wallet.participant.name}}
    wallet, _ = resolve_payment_target(db, vendor, qr_token, participant_code)
    return {"kind": "wallet", "wallet": {"id": wallet.id, "participant_code": wallet.participant.participant_code, "participant_name": wallet.participant.name, "group": wallet.participant.group_name, "balance_minor": wallet.balance_minor, "reserved_minor": reserved_minor(db, wallet.id), "currency": wallet.event.currency}}


@router.post("/payments")
def create_payment(
    payload: PaymentCreate, vendor: Vendor = Depends(require_vendor_csrf), db: Session = Depends(get_db)
) -> dict:
    row = create_vendor_payment(
        db, vendor, payload.amount_minor, payload.request_key, payload.qr_token,
        payload.participant_code, payload.wallet_id,
    )
    return {"transaction": {"id": row.id, "reference": row.reference, "status": row.status, "amount_minor": row.amount_minor}}


@router.get("/payments/{transaction_id}")
def payment_status(transaction_id: int, vendor: Vendor = Depends(require_vendor), db: Session = Depends(get_db)) -> dict:
    row = db.scalar(select(MoneyTransaction).where(MoneyTransaction.id == transaction_id, MoneyTransaction.vendor_id == vendor.id))
    if not row:
        raise ApiError(404, "not_found", "Payment was not found.")
    return {"transaction": {"id": row.id, "reference": row.reference, "status": row.status, "amount_minor": row.amount_minor}}


@router.post("/coupons/redeem")
def redeem_coupon(
    payload: CouponRedeem, vendor: Vendor = Depends(require_vendor_csrf), db: Session = Depends(get_db)
) -> dict:
    coupon_id = coupon_id_from_token(payload.token)
    coupon = db.scalar(
        select(CouponInstance)
        .where(CouponInstance.id == (coupon_id or 0), CouponInstance.event_id == vendor.event_id)
        .with_for_update()
    )
    if not coupon or coupon.status != CouponStatus.available:
        raise ApiError(409, "coupon_unavailable", "Coupon is invalid or unavailable.")
    template = db.get(CouponTemplate, coupon.template_id)
    wallet = db.scalar(select(Wallet).where(Wallet.id == coupon.wallet_id).with_for_update())
    if not template or not wallet or not wallet.enabled or (template.vendor_id and template.vendor_id != vendor.id):
        raise ApiError(409, "coupon_unavailable", "Coupon is invalid or unavailable.")
    coupon.status = CouponStatus.redeemed
    coupon.redeemed_at = utcnow()
    coupon.redeemed_by_vendor_id = vendor.id
    audit = CouponAudit(
        event_id=vendor.event_id, coupon_id=coupon.id, wallet_id=wallet.id, vendor_id=vendor.id,
        reference=reference("CPR"), action="redeemed", coupon_name=template.name,
        participant_code=wallet.participant.participant_code, participant_name=wallet.participant.name,
        vendor_name=vendor.name, actor=f"vendor:{vendor.id}",
    )
    db.add(audit)
    db.commit()
    return {"redemption": {"reference": audit.reference, "coupon_name": template.name, "participant_name": wallet.participant.name}}
