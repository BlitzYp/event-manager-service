from datetime import timedelta
from uuid import uuid4

from app.database import SessionLocal, utcnow
from app.models import (
    ActionType,
    AdminUser,
    Event,
    EventMode,
    EventStatus,
    Participant,
    ScheduledAction,
    ScheduleType,
    Wallet,
)
from app.routers.admin import apply_action_wallet_scope, delete_participant
from app.schemas import ActionWalletScope
from app.services import create_participant_with_wallet


def test_participant_delete_and_scoped_action_execution() -> None:
    db = SessionLocal()
    event_id: int | None = None
    try:
        suffix = uuid4().hex[:10]
        event = Event(
            code=f"test-{suffix}",
            name="Scoped action test",
            status=EventStatus.active,
            mode=EventMode.money,
            currency="EUR",
            default_balance_minor=0,
        )
        db.add(event)
        db.flush()
        event_id = event.id

        first, first_wallet, _ = create_participant_with_wallet(
            db, event, "P-1", "First participant", "Group A", None
        )
        _, second_wallet, _ = create_participant_with_wallet(
            db, event, "P-2", "Second participant", "Group B", None
        )
        removable, _, _ = create_participant_with_wallet(
            db, event, "P-3", "Removable participant", None, None
        )
        first_wallet.enabled = False
        second_wallet.enabled = False
        action = ScheduledAction(
            event_id=event.id,
            name="Activate selected wallets",
            action_type=ActionType.activate_wallets,
            schedule_type=ScheduleType.once,
            execute_at=utcnow() + timedelta(days=1),
            created_by="test",
        )
        db.add(action)
        db.commit()

        admin = AdminUser(id=999_999, email="test@example.invalid", password_hash="unused")
        result = apply_action_wallet_scope(
            event.id,
            action.id,
            ActionWalletScope(operation="execute", wallet_ids=[first_wallet.id]),
            admin,
            db,
        )
        assert result["affected_count"] == 1
        db.expire_all()
        assert db.get(Wallet, first_wallet.id).enabled is True
        assert db.get(Wallet, second_wallet.id).enabled is False

        response = delete_participant(event.id, removable.id, admin, db)
        assert response.status_code == 204
        assert db.get(Participant, removable.id) is None
        assert db.get(Participant, first.id) is not None
    finally:
        db.rollback()
        if event_id is not None:
            event = db.get(Event, event_id)
            if event:
                db.delete(event)
                db.commit()
        db.close()
