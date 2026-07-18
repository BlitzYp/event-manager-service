from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    CouponInstance,
    CouponStatus,
    CouponTemplate,
    MoneyTransaction,
    TransactionStatus,
)
from ..schemas import DecisionRequest
from ..security import coupon_token
from ..services import create_payment_qr, decide_payment, reserved_minor, wallet_for_access_token

router = APIRouter(prefix="/participant", tags=["participant-wallet"])


def wallet_payload(db: Session, access_token: str) -> dict:
    wallet = wallet_for_access_token(db, access_token)
    participant, event = wallet.participant, wallet.event
    pending = list(
        db.scalars(
            select(MoneyTransaction)
            .where(
                MoneyTransaction.wallet_id == wallet.id,
                MoneyTransaction.status == TransactionStatus.pending,
            )
            .order_by(MoneyTransaction.created_at.desc())
        )
    )
    transactions = list(
        db.scalars(
            select(MoneyTransaction)
            .where(MoneyTransaction.wallet_id == wallet.id)
            .order_by(MoneyTransaction.created_at.desc())
            .limit(20)
        )
    )
    coupons = db.execute(
        select(CouponInstance, CouponTemplate)
        .join(CouponTemplate, CouponTemplate.id == CouponInstance.template_id)
        .where(CouponInstance.wallet_id == wallet.id, CouponInstance.status != CouponStatus.removed)
        .order_by(CouponTemplate.sort_order, CouponTemplate.name)
    ).all()
    return {
        "event": {
            "id": event.id,
            "name": event.name,
            "mode": event.mode,
            "currency": event.currency,
        },
        "participant": {
            "code": participant.participant_code,
            "name": participant.name,
            "group": participant.group_name,
        },
        "wallet": {
            "id": wallet.id,
            "enabled": wallet.enabled,
            "balance_minor": wallet.balance_minor,
            "reserved_minor": reserved_minor(db, wallet.id),
        },
        "pending": [transaction_payload(row) for row in pending],
        "transactions": [transaction_payload(row) for row in transactions],
        "coupons": [
            {
                "id": coupon.id,
                "name": template.name,
                "status": coupon.status,
                "qr_token": coupon_token(coupon.id)
                if coupon.status == CouponStatus.available
                else None,
            }
            for coupon, template in coupons
        ],
    }


def transaction_payload(row: MoneyTransaction) -> dict:
    return {
        "id": row.id,
        "reference": row.reference,
        "type": row.type,
        "status": row.status,
        "amount_minor": row.amount_minor,
        "vendor_name": row.vendor_name,
        "created_at": row.created_at,
        "expires_at": row.expires_at,
    }


@router.get("/wallet/{access_token}")
def state(access_token: str, db: Session = Depends(get_db)) -> dict:
    return wallet_payload(db, access_token)


@router.post("/wallet/{access_token}/payment-qr")
def payment_qr(access_token: str, db: Session = Depends(get_db)) -> dict:
    wallet = wallet_for_access_token(db, access_token, lock=True)
    token, ttl = create_payment_qr(db, wallet)
    db.commit()
    return {"token": token, "ttl_seconds": ttl}


@router.post("/wallet/{access_token}/payments/{transaction_id}/decision")
def payment_decision(
    access_token: str, transaction_id: int, payload: DecisionRequest, db: Session = Depends(get_db)
) -> dict:
    wallet = wallet_for_access_token(db, access_token)
    return {
        "transaction": transaction_payload(
            decide_payment(db, wallet, transaction_id, payload.decision)
        )
    }
