from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import utcnow
from .email_service import send_template_email
from .models import (
    ActionType,
    ActionWalletOverride,
    CouponAudit,
    CouponInstance,
    CouponStatus,
    CouponTemplate,
    EmailDeliveryStatus,
    EmailTemplate,
    Event,
    MoneyTransaction,
    Participant,
    PaymentQrGrant,
    ScheduledAction,
    ScheduledActionRun,
    ScheduleType,
    TransactionStatus,
    Vendor,
    Wallet,
    WalletAccessToken,
)
from .services import issue_coupons, reference


def target_wallet_ids(db: Session, action: ScheduledAction) -> list[int]:
    excluded = select(ActionWalletOverride.wallet_id).where(
        ActionWalletOverride.action_id == action.id,
        ActionWalletOverride.included.is_(False),
    )
    return list(
        db.scalars(
            select(Wallet.id).where(Wallet.event_id == action.event_id, Wallet.id.not_in(excluded))
        )
    )


def record_coupon_audit(db: Session, coupon: CouponInstance, action_name: str, actor: str) -> None:
    template = db.get(CouponTemplate, coupon.template_id)
    wallet = db.get(Wallet, coupon.wallet_id)
    if not template or not wallet:
        return
    vendor = db.get(Vendor, template.vendor_id) if template.vendor_id else None
    db.add(
        CouponAudit(
            event_id=coupon.event_id,
            coupon_id=coupon.id,
            wallet_id=wallet.id,
            vendor_id=template.vendor_id,
            reference=reference("CPA"),
            action=action_name,
            coupon_name=template.name,
            participant_code=wallet.participant.participant_code,
            participant_name=wallet.participant.name,
            vendor_name=vendor.name if vendor else None,
            actor=actor,
        )
    )


def execute_action(
    db: Session,
    action: ScheduledAction,
    run_type: str,
    actor: str,
    advance_schedule: bool = True,
    wallet_ids_override: list[int] | None = None,
) -> ScheduledActionRun:
    schedule_key = action.execute_at.strftime("%Y%m%d%H%M")
    run_key = f"{action.id}:{schedule_key}:{run_type}"
    existing = db.scalar(select(ScheduledActionRun).where(ScheduledActionRun.run_key == run_key))
    if existing:
        return existing
    wallet_ids = (
        list(dict.fromkeys(wallet_ids_override))
        if wallet_ids_override is not None
        else target_wallet_ids(db, action)
    )
    affected = 0
    run_success = True
    message = "No matching wallets."
    if action.action_type == ActionType.create_wallets:
        message = "Participants receive wallets when created; no missing wallets were found."
    elif action.action_type in {ActionType.activate_wallets, ActionType.deactivate_wallets}:
        enabled = action.action_type == ActionType.activate_wallets
        for wallet in db.scalars(select(Wallet).where(Wallet.id.in_(wallet_ids)).with_for_update()):
            if wallet.enabled != enabled:
                wallet.enabled = enabled
                affected += 1
        message = f"Updated {affected} wallets."
    elif action.action_type == ActionType.delete_wallets:
        for wallet in db.scalars(select(Wallet).where(Wallet.id.in_(wallet_ids)).with_for_update()):
            history = db.scalar(
                select(func.count(MoneyTransaction.id)).where(
                    MoneyTransaction.wallet_id == wallet.id
                )
            )
            coupon_count = db.scalar(
                select(func.count(CouponInstance.id)).where(CouponInstance.wallet_id == wallet.id)
            )
            if history or coupon_count:
                wallet.enabled = False
                continue
            db.query(PaymentQrGrant).filter(PaymentQrGrant.wallet_id == wallet.id).delete()
            db.query(WalletAccessToken).filter(WalletAccessToken.wallet_id == wallet.id).delete()
            db.delete(wallet)
            affected += 1
        message = f"Deleted {affected} empty wallets; wallets with audit history were disabled."
    elif action.action_type in {ActionType.issue_coupons, ActionType.refill_coupons}:
        affected = issue_coupons(db, action.event_id, wallet_ids, actor)
        message = f"Issued {affected} coupons."
    elif action.action_type in {ActionType.disable_coupons, ActionType.enable_coupons}:
        source = (
            CouponStatus.available
            if action.action_type == ActionType.disable_coupons
            else CouponStatus.disabled
        )
        target = (
            CouponStatus.disabled if source == CouponStatus.available else CouponStatus.available
        )
        coupon_rows = list(
            db.scalars(
                select(CouponInstance)
                .where(CouponInstance.wallet_id.in_(wallet_ids), CouponInstance.status == source)
                .with_for_update()
            )
        )
        for coupon in coupon_rows:
            coupon.status = target
            record_coupon_audit(db, coupon, target.value, actor)
        affected = len(coupon_rows)
        message = f"Updated {affected} coupons."
    elif action.action_type == ActionType.send_email:
        template = db.scalar(
            select(EmailTemplate).where(
                EmailTemplate.id == action.email_template_id,
                EmailTemplate.event_id == action.event_id,
                EmailTemplate.archived_at.is_(None),
            )
        )
        event = db.get(Event, action.event_id)
        if not template or not event:
            run_success = False
            message = "The configured email template is no longer available."
        else:
            participants = list(
                db.scalars(
                    select(Participant)
                    .join(Wallet, Wallet.participant_id == Participant.id)
                    .where(
                        Participant.event_id == action.event_id,
                        Wallet.id.in_(wallet_ids),
                    )
                    .order_by(Participant.name)
                )
            )
            sent = failed = simulated = skipped = 0
            delivery_number = 0
            for participant in participants:
                if not participant.email:
                    skipped += 1
                    continue
                delivery = send_template_email(
                    db,
                    event=event,
                    template=template,
                    participant=participant,
                    actor=actor,
                    subject_override=action.email_subject,
                    development_delivery_number=delivery_number,
                )
                delivery_number += 1
                if delivery.status == EmailDeliveryStatus.sent:
                    sent += 1
                elif delivery.status == EmailDeliveryStatus.failed:
                    failed += 1
                else:
                    simulated += 1
            affected = sent
            run_success = failed == 0
            message = (
                f"Emails sent: {sent}; simulated: {simulated}; "
                f"without an email address: {skipped}; failed: {failed}."
            )
    run = ScheduledActionRun(
        action_id=action.id,
        run_key=run_key,
        run_type=run_type,
        affected_count=affected,
        success=run_success,
        message=message,
        executed_by=actor,
    )
    db.add(run)
    if advance_schedule:
        advance_action(db, action)
    db.commit()
    return run


def advance_action(db: Session, action: ScheduledAction) -> None:
    completed = True
    if action.schedule_type == ScheduleType.daily:
        next_at = action.execute_at + timedelta(days=1)
        if action.schedule_end and next_at.date() <= action.schedule_end:
            action.execute_at = next_at
            completed = False
    if completed:
        action.completed_at = utcnow()
        action.enabled = False
        if action.auto_delete:
            db.delete(action)


def expire_pending_payments(db: Session) -> int:
    rows = list(
        db.scalars(
            select(MoneyTransaction)
            .where(
                MoneyTransaction.status == TransactionStatus.pending,
                MoneyTransaction.expires_at <= utcnow(),
            )
            .with_for_update()
        )
    )
    for row in rows:
        row.status = TransactionStatus.cancelled
        row.decision_at = utcnow()
        row.decided_by = "system:expired"
    db.commit()
    return len(rows)
