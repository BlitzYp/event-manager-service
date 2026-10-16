"""Wallet availability, balance adjustments, and transaction reversals."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db, utcnow
from ..dependencies import require_admin_csrf
from ..errors import ApiError
from ..models import AdminUser, MoneyTransaction, TransactionStatus, TransactionType, Wallet
from ..schemas import AdjustmentRequest
from ..services import event_supports, reference, reserved_minor

router = APIRouter()


@router.patch("/events/{event_id}/wallets/{wallet_id}/enabled")
def set_wallet_enabled(
    event_id: int,
    wallet_id: int,
    enabled: bool,
    _: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    """Commit wallet activation or suspension and return a confirmation message."""
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
    """Lock a wallet, commit a balance adjustment with a ledger record, and return its reference."""
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
    """Lock the transaction and wallet, commit a reversal, and return its new reference."""
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
