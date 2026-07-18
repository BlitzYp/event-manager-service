from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, utcnow
from app.errors import ApiError
from app.models import (
    Event,
    EventMode,
    EventStatus,
    Participant,
    Wallet,
    WalletAccessToken,
)
from app.security import new_token, token_hash
from app.services import (
    create_wallet_preview_token,
    wallet_for_access_token,
)


def test_preview_token_expires_without_replacing_participant_token() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        event = Event(
            id=1,
            code="preview",
            name="Preview event",
            status=EventStatus.active,
            mode=EventMode.money,
            default_balance_minor=0,
        )
        participant = Participant(
            id=1,
            event_id=event.id,
            participant_code="P-001",
            name="Preview Person",
        )
        wallet = Wallet(id=1, event_id=event.id, participant_id=participant.id)
        participant_token = new_token()
        db.add_all(
            [
                event,
                participant,
                wallet,
                WalletAccessToken(
                    id=1,
                    wallet_id=wallet.id,
                    token_hash=token_hash(participant_token),
                ),
            ]
        )
        preview_token, _ = create_wallet_preview_token(db, wallet)
        preview_row = next(
            row
            for row in db.new
            if isinstance(row, WalletAccessToken) and row.token_hash == token_hash(preview_token)
        )
        preview_row.id = 2
        db.commit()

        assert wallet_for_access_token(db, participant_token).id == wallet.id
        assert wallet_for_access_token(db, preview_token).id == wallet.id

        preview_row.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()

        with pytest.raises(ApiError):
            wallet_for_access_token(db, preview_token)
        assert wallet_for_access_token(db, participant_token).id == wallet.id
