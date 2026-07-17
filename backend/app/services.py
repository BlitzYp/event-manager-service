from __future__ import annotations

import csv
import io
import secrets
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .database import utcnow
from .errors import ApiError
from .models import (
    CouponAudit,
    CouponInstance,
    CouponStatus,
    CouponTemplate,
    Event,
    EventMode,
    EventStatus,
    MoneyTransaction,
    Participant,
    PaymentQrGrant,
    TransactionStatus,
    TransactionType,
    Vendor,
    Wallet,
    WalletAccessToken,
)
from .security import coupon_token, new_token, token_hash


def reference(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(8).upper()}"


def event_supports(event: Event, system: str) -> bool:
    return event.mode.value == system or event.mode == EventMode.both


def create_participant_with_wallet(
    db: Session,
    event: Event,
    participant_code: str,
    name: str,
    group_name: str | None,
    email: str | None,
    initial_balance_minor: int | None = None,
) -> tuple[Participant, Wallet, str]:
    amount = event.default_balance_minor if initial_balance_minor is None else initial_balance_minor
    if not event_supports(event, "money"):
        amount = 0
    participant = Participant(
        event_id=event.id,
        participant_code=participant_code.strip(),
        name=name.strip(),
        group_name=group_name.strip() if group_name else None,
        email=email,
    )
    db.add(participant)
    db.flush()
    wallet = Wallet(event_id=event.id, participant_id=participant.id, balance_minor=amount)
    db.add(wallet)
    db.flush()
    raw_token = new_token()
    db.add(WalletAccessToken(wallet_id=wallet.id, token_hash=token_hash(raw_token)))
    if amount:
        db.add(
            MoneyTransaction(
                event_id=event.id,
                wallet_id=wallet.id,
                reference=reference("INIT"),
                type=TransactionType.initial_credit,
                status=TransactionStatus.approved,
                amount_minor=amount,
                participant_code=participant.participant_code,
                participant_name=participant.name,
                group_name=participant.group_name,
                actor="system:participant-create",
                decided_by="system:participant-create",
                decision_at=utcnow(),
            )
        )
    return participant, wallet, raw_token


def rotate_wallet_token(db: Session, wallet: Wallet) -> str:
    now = utcnow()
    for row in db.scalars(
        select(WalletAccessToken)
        .where(WalletAccessToken.wallet_id == wallet.id, WalletAccessToken.revoked_at.is_(None))
        .with_for_update()
    ):
        row.revoked_at = now
    raw_token = new_token()
    db.add(WalletAccessToken(wallet_id=wallet.id, token_hash=token_hash(raw_token)))
    return raw_token


def wallet_for_access_token(db: Session, raw_token: str, lock: bool = False) -> Wallet:
    query = (
        select(Wallet)
        .join(WalletAccessToken, WalletAccessToken.wallet_id == Wallet.id)
        .where(
            WalletAccessToken.token_hash == token_hash(raw_token),
            WalletAccessToken.revoked_at.is_(None),
        )
    )
    if lock:
        query = query.with_for_update()
    wallet = db.scalar(query)
    if not wallet:
        raise ApiError(404, "wallet_unavailable", "Wallet link is invalid or unavailable.")
    return wallet


def reserved_minor(db: Session, wallet_id: int) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(MoneyTransaction.amount_minor), 0)).where(
                MoneyTransaction.wallet_id == wallet_id,
                MoneyTransaction.status == TransactionStatus.pending,
                MoneyTransaction.expires_at > utcnow(),
            )
        )
        or 0
    )


def create_payment_qr(db: Session, wallet: Wallet) -> tuple[str, int]:
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
    db: Session, vendor: Vendor, qr_token: str | None, participant_code: str | None, lock: bool = False
) -> tuple[Wallet, PaymentQrGrant | None]:
    query = select(Wallet).join(Participant).where(
        Wallet.event_id == vendor.event_id,
        Participant.participant_code == (participant_code or ""),
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
            query = select(Wallet).where(Wallet.id == grant.wallet_id, Wallet.event_id == vendor.event_id)
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
    status = TransactionStatus.pending if wallet.event.approval_required else TransactionStatus.approved
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


def issue_coupons(db: Session, event_id: int, wallet_ids: list[int] | None, actor: str) -> int:
    templates = list(
        db.scalars(select(CouponTemplate).where(CouponTemplate.event_id == event_id, CouponTemplate.active.is_(True)))
    )
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
                    actor=actor,
                )
            )
            issued += 1
    return issued


def validate_participant_csv(content: bytes) -> list[dict[str, str | None]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ApiError(422, "invalid_csv", "CSV must use UTF-8 encoding.") from exc
    reader = csv.DictReader(io.StringIO(text))
    required = {"participant_code", "name"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise ApiError(422, "invalid_csv", "CSV requires participant_code and name columns.")
    rows: list[dict[str, str | None]] = []
    errors: list[str] = []
    seen: set[str] = set()
    for line, raw in enumerate(reader, start=2):
        code = (raw.get("participant_code") or "").strip()
        name = (raw.get("name") or "").strip()
        if not code or not name:
            errors.append(f"Row {line}: participant_code and name are required.")
        elif code in seen:
            errors.append(f"Row {line}: duplicate participant_code '{code}'.")
        seen.add(code)
        rows.append(
            {"participant_code": code, "name": name, "group": (raw.get("group") or "").strip() or None, "email": (raw.get("email") or "").strip() or None}
        )
    if errors:
        raise ApiError(422, "invalid_csv", " ".join(errors[:20]))
    return rows
