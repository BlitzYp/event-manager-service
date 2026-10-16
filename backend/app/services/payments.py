"""Payment QR grants and locked payment creation or approval."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import utcnow
from ..errors import ApiError
from ..models import (
    MoneyTransaction,
    Participant,
    PaymentQrGrant,
    TransactionStatus,
    TransactionType,
    Vendor,
    Wallet,
)
from ..security import new_token, token_hash
from .common import event_supports, reference
from .wallets import reserved_minor


def create_payment_qr(db: Session, wallet: Wallet) -> tuple[str, int]:
    """Stage a single-use QR grant, retiring previous grants; return (raw token, TTL seconds).

    The caller must hold the wallet lock and commit the grant changes.
    """
    if not wallet.enabled or not event_supports(wallet.event, "money"):
        raise ApiError(409, "wallet_unavailable", "Wallet is not available for payments.")
    now = utcnow()
    for grant in db.scalars(
        select(PaymentQrGrant).where(
            PaymentQrGrant.wallet_id == wallet.id,
            PaymentQrGrant.consumed_at.is_(None),
            PaymentQrGrant.expires_at > now,
        )
    ):
        grant.consumed_at = now
    raw = new_token(24)
    db.add(
        PaymentQrGrant(
            wallet_id=wallet.id,
            token_hash=token_hash(raw),
            expires_at=now + timedelta(seconds=wallet.event.qr_ttl_seconds),
        )
    )
    return raw, wallet.event.qr_ttl_seconds


def resolve_payment_target(
    db: Session,
    vendor: Vendor,
    qr_token: str | None,
    participant_code: str | None,
    lock: bool = False,
) -> tuple[Wallet, PaymentQrGrant | None]:
    """Return an enabled wallet in the vendor event and an optional locked QR grant."""
    query = (
        select(Wallet)
        .join(Participant)
        .where(
            Wallet.event_id == vendor.event_id,
            Participant.participant_code == (participant_code or ""),
        )
    )
    grant = None
    if qr_token:
        grant_query = (
            select(PaymentQrGrant)
            .where(
                PaymentQrGrant.token_hash == token_hash(qr_token),
                PaymentQrGrant.expires_at > utcnow(),
                PaymentQrGrant.consumed_at.is_(None),
            )
            .with_for_update()
        )
        grant = db.scalar(grant_query)
        if grant:
            query = select(Wallet).where(
                Wallet.id == grant.wallet_id, Wallet.event_id == vendor.event_id
            )
    if lock:
        query = query.with_for_update()
    wallet = db.scalar(query)
    if not wallet or not wallet.enabled:
        raise ApiError(404, "wallet_unavailable", "Wallet or QR code is invalid or unavailable.")
    return wallet, grant


def create_vendor_payment(
    db: Session,
    vendor: Vendor,
    amount_minor: int,
    request_key: str,
    qr_token: str | None = None,
    participant_code: str | None = None,
    wallet_id: int | None = None,
) -> MoneyTransaction:
    """Lock the target wallet and commit an idempotent vendor payment.

    Return the existing or newly committed ledger record. Immediate payments deduct
    the balance; pending payments reserve funds until approval or expiration.
    """
    existing = db.scalar(
        select(MoneyTransaction).where(
            MoneyTransaction.event_id == vendor.event_id,
            MoneyTransaction.request_key == request_key,
        )
    )
    if existing:
        return existing
    wallet, grant = resolve_payment_target(db, vendor, qr_token, participant_code, lock=True)
    if wallet_id and wallet.id != wallet_id:
        raise ApiError(409, "wallet_mismatch", "Selected wallet does not match the payment token.")
    if qr_token and not grant:
        raise ApiError(404, "wallet_unavailable", "Wallet or QR code is invalid or unavailable.")
    available = wallet.balance_minor - reserved_minor(db, wallet.id)
    if amount_minor > available:
        raise ApiError(409, "insufficient_funds", "Wallet has insufficient available funds.")
    now = utcnow()
    if grant:
        grant.consumed_at = now
    participant = wallet.participant
    status = (
        TransactionStatus.pending if wallet.event.approval_required else TransactionStatus.approved
    )
    transaction = MoneyTransaction(
        event_id=wallet.event_id,
        wallet_id=wallet.id,
        vendor_id=vendor.id,
        reference=reference("PAY"),
        request_key=request_key,
        type=TransactionType.vendor_debit,
        status=status,
        amount_minor=amount_minor,
        participant_code=participant.participant_code,
        participant_name=participant.name,
        group_name=participant.group_name,
        vendor_name=vendor.name,
        actor=f"vendor:{vendor.id}",
        decided_by=None if status == TransactionStatus.pending else f"vendor:{vendor.id}",
        decision_at=None if status == TransactionStatus.pending else now,
        expires_at=(now + timedelta(minutes=wallet.event.pending_payment_minutes))
        if status == TransactionStatus.pending
        else None,
    )
    if status == TransactionStatus.approved:
        wallet.balance_minor -= amount_minor
    db.add(transaction)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        duplicate = db.scalar(
            select(MoneyTransaction).where(
                MoneyTransaction.event_id == vendor.event_id,
                MoneyTransaction.request_key == request_key,
            )
        )
        if duplicate:
            return duplicate
        raise
    db.refresh(transaction)
    return transaction


def decide_payment(
    db: Session, wallet: Wallet, transaction_id: int, decision: str
) -> MoneyTransaction:
    """Lock a pending payment and wallet, commit approval/rejection, and return the record.

    Expired requests are committed as cancelled before raising an API error.
    """
    transaction = db.scalar(
        select(MoneyTransaction)
        .where(
            MoneyTransaction.id == transaction_id,
            MoneyTransaction.wallet_id == wallet.id,
            MoneyTransaction.status == TransactionStatus.pending,
        )
        .with_for_update()
    )
    locked_wallet = db.scalar(select(Wallet).where(Wallet.id == wallet.id).with_for_update())
    if not transaction or not locked_wallet:
        raise ApiError(409, "payment_not_pending", "Payment is no longer pending.")
    now = utcnow()
    if transaction.expires_at and transaction.expires_at <= now:
        transaction.status = TransactionStatus.cancelled
        transaction.decision_at = now
        transaction.decided_by = "system:expired"
        db.commit()
        raise ApiError(409, "payment_expired", "Payment request has expired.")
    if decision == "approved":
        if transaction.amount_minor > locked_wallet.balance_minor:
            raise ApiError(409, "insufficient_funds", "Wallet has insufficient funds.")
        locked_wallet.balance_minor -= transaction.amount_minor
        transaction.status = TransactionStatus.approved
    else:
        transaction.status = TransactionStatus.rejected
    transaction.decision_at = now
    transaction.decided_by = f"participant:{wallet.participant_id}"
    db.commit()
    db.refresh(transaction)
    return transaction
