"""Participant creation and CSV validation; callers commit created records."""

from __future__ import annotations

import csv
import io

from sqlalchemy.orm import Session

from ..database import utcnow
from ..errors import ApiError
from ..models import (
    Event,
    MoneyTransaction,
    Participant,
    TransactionStatus,
    TransactionType,
    Wallet,
    WalletAccessToken,
)
from ..security import new_token, token_hash
from .common import event_supports, reference


def create_participant_with_wallet(
    db: Session,
    event: Event,
    participant_code: str,
    name: str,
    group_name: str | None,
    email: str | None,
    initial_balance_minor: int | None = None,
) -> tuple[Participant, Wallet, str]:
    """Stage a participant, wallet, access-token hash, and initial credit.

    Return (participant, wallet, raw token); the caller must commit. The raw token
    is returned once for link delivery and is never stored in the database.
    """
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


def validate_participant_csv(content: bytes) -> list[dict[str, str | None]]:
    """Return normalized UTF-8 CSV rows or raise validation errors before any database writes."""
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
            {
                "participant_code": code,
                "name": name,
                "group": (raw.get("group") or "").strip() or None,
                "email": (raw.get("email") or "").strip() or None,
            }
        )
    if errors:
        raise ApiError(422, "invalid_csv", " ".join(errors[:20]))
    return rows
