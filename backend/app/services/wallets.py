"""Wallet link lifecycle and reserved-balance queries; callers commit token changes."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import utcnow
from ..errors import ApiError
from ..models import MoneyTransaction, TransactionStatus, Wallet, WalletAccessToken
from ..security import new_token, token_hash


def rotate_wallet_token(db: Session, wallet: Wallet) -> str:
    """Stage revocation of old access tokens and return a new raw token; the caller commits."""
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


def create_wallet_preview_token(db: Session, wallet: Wallet) -> tuple[str, datetime]:
    """Stage a short-lived access token and return (raw token, expiry); the caller commits."""
    raw_token = new_token()
    expires_at = utcnow() + timedelta(minutes=settings.admin_wallet_preview_minutes)
    db.add(
        WalletAccessToken(
            wallet_id=wallet.id,
            token_hash=token_hash(raw_token),
            expires_at=expires_at,
        )
    )
    return raw_token, expires_at


def wallet_for_access_token(db: Session, raw_token: str, lock: bool = False) -> Wallet:
    """Return the wallet for a live hashed token, optionally locked; reject invalid links."""
    now = utcnow()
    query = (
        select(Wallet)
        .join(WalletAccessToken, WalletAccessToken.wallet_id == Wallet.id)
        .where(
            WalletAccessToken.token_hash == token_hash(raw_token),
            WalletAccessToken.revoked_at.is_(None),
            or_(WalletAccessToken.expires_at.is_(None), WalletAccessToken.expires_at > now),
        )
    )
    if lock:
        query = query.with_for_update()
    wallet = db.scalar(query)
    if not wallet:
        raise ApiError(404, "wallet_unavailable", "Wallet link is invalid or unavailable.")
    return wallet


def reserved_minor(db: Session, wallet_id: int) -> int:
    """Return minor units reserved by unexpired pending payments, without changing the balance."""
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
