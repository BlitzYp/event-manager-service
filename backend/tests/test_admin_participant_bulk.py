from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.database import SessionLocal, utcnow
from app.dependencies import require_vendor
from app.errors import ApiError
from app.models import (
    ActionType,
    AdminUser,
    CouponInstance,
    CouponStatus,
    CouponTemplate,
    Event,
    EventMode,
    EventStatus,
    Participant,
    ScheduledAction,
    ScheduleType,
    Vendor,
    VendorSession,
    Wallet,
)
from app.routers.admin import (
    apply_action_wallet_scope,
    delete_participant,
    list_participants,
    update_event,
)
from app.schemas import ActionWalletScope, EventUpdate
from app.security import token_hash
from app.services import create_participant_with_wallet, issue_coupons


def test_archiving_event_revokes_and_rejects_vendor_sessions() -> None:
    db = SessionLocal()
    event_id: int | None = None
    try:
        suffix = uuid4().hex[:10]
        event = Event(
            code=f"archive-{suffix}",
            name="Archived vendor event",
            status=EventStatus.active,
            mode=EventMode.money,
            currency="EUR",
            default_balance_minor=0,
        )
        db.add(event)
        db.flush()
        event_id = event.id
        vendor = Vendor(
            event_id=event.id,
            name="Test vendor",
            pin_lookup=f"lookup-{suffix}",
            pin_hash="unused",
            active=True,
        )
        db.add(vendor)
        db.flush()
        raw_session = f"vendor-session-{suffix}"
        session = VendorSession(
            vendor_id=vendor.id,
            token_hash=token_hash(raw_session),
            csrf_hash=token_hash("csrf"),
        )
        db.add(session)
        db.commit()

        update_event(
            event.id,
            EventUpdate(
                code=event.code,
                name=event.name,
                status=EventStatus.archived,
                mode=event.mode,
                currency=event.currency,
                default_balance_minor=event.default_balance_minor,
                qr_ttl_seconds=event.qr_ttl_seconds,
                approval_required=event.approval_required,
                pending_payment_minutes=event.pending_payment_minutes,
            ),
            AdminUser(id=999_999, email="test@example.invalid", password_hash="unused"),
            db,
        )
        db.refresh(session)
        assert session.revoked_at is not None

        replacement_raw = f"replacement-session-{suffix}"
        db.add(
            VendorSession(
                vendor_id=vendor.id,
                token_hash=token_hash(replacement_raw),
                csrf_hash=token_hash("replacement-csrf"),
            )
        )
        db.commit()
        with pytest.raises(ApiError) as error:
            require_vendor(db, replacement_raw)
        assert error.value.code == "authentication_required"
    finally:
        db.rollback()
        if event_id is not None:
            event = db.get(Event, event_id)
            if event:
                db.delete(event)
                db.commit()
        db.close()


def test_multiple_events_can_be_active_at_the_same_time() -> None:
    db = SessionLocal()
    event_ids: list[int] = []
    owner_ids: list[int] = []
    try:
        suffix = uuid4().hex[:10]
        first_owner = AdminUser(
            email=f"owner-a-{suffix}@example.invalid", password_hash="unused"
        )
        second_owner = AdminUser(
            email=f"owner-b-{suffix}@example.invalid", password_hash="unused"
        )
        db.add_all([first_owner, second_owner])
        db.flush()
        owner_ids = [first_owner.id, second_owner.id]
        first = Event(
            admin_id=first_owner.id,
            code=f"active-a-{suffix}",
            name="First active event",
            status=EventStatus.draft,
            mode=EventMode.money,
            currency="EUR",
            default_balance_minor=0,
        )
        second = Event(
            admin_id=second_owner.id,
            code=f"active-b-{suffix}",
            name="Second active event",
            status=EventStatus.active,
            mode=EventMode.coupons,
            currency="EUR",
            default_balance_minor=0,
        )
        db.add_all([first, second])
        db.commit()
        event_ids = [first.id, second.id]

        update_event(
            first.id,
            EventUpdate(
                code=first.code,
                name=first.name,
                status=EventStatus.active,
                mode=first.mode,
                currency=first.currency,
                default_balance_minor=first.default_balance_minor,
                qr_ttl_seconds=first.qr_ttl_seconds,
                approval_required=first.approval_required,
                pending_payment_minutes=first.pending_payment_minutes,
            ),
            first_owner,
            db,
        )

        db.expire_all()
        assert db.get(Event, first.id).status == EventStatus.active
        assert db.get(Event, second.id).status == EventStatus.active
    finally:
        db.rollback()
        for event_id in event_ids:
            event = db.get(Event, event_id)
            if event:
                db.delete(event)
        db.flush()
        for owner_id in owner_ids:
            owner = db.get(AdminUser, owner_id)
            if owner:
                db.delete(owner)
        db.commit()
        db.close()


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


def test_selected_coupon_issuance_and_participant_summary() -> None:
    db = SessionLocal()
    try:
        suffix = uuid4().hex[:10]
        event = Event(
            code=f"coupon-{suffix}",
            name="Selected coupon test",
            status=EventStatus.active,
            mode=EventMode.coupons,
            currency="EUR",
            default_balance_minor=0,
        )
        db.add(event)
        db.flush()
        _, wallet, _ = create_participant_with_wallet(
            db, event, "C-1", "Coupon participant", "Group C", None
        )
        selected = CouponTemplate(event_id=event.id, name="Lunch", sort_order=1, active=True)
        unselected = CouponTemplate(event_id=event.id, name="Drink", sort_order=2, active=True)
        db.add_all([selected, unselected])
        db.flush()

        assert issue_coupons(
            db, event.id, None, "test", template_ids=[selected.id]
        ) == 1
        assert issue_coupons(
            db, event.id, None, "test", template_ids=[selected.id]
        ) == 0
        coupons = list(
            db.scalars(select(CouponInstance).where(CouponInstance.wallet_id == wallet.id))
        )
        assert [(coupon.template_id, coupon.status) for coupon in coupons] == [
            (selected.id, CouponStatus.available)
        ]

        admin = AdminUser(id=999_999, email="test@example.invalid", password_hash="unused")
        result = list_participants(event.id, "", "", None, admin, db)
        assert result["participants"][0]["coupons"] == {
            "available": 1,
            "disabled": 0,
            "redeemed": 0,
            "total": 1,
        }
    finally:
        db.rollback()
        db.close()
