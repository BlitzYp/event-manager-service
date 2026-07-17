from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import utcnow
from .models import (
    ActionType,
    ActionWalletOverride,
    CouponAudit,
    CouponInstance,
    CouponStatus,
    CouponTemplate,
    MoneyTransaction,
    PaymentQrGrant,
    ScheduledAction,
    ScheduledActionRun,
    ScheduleType,
    TransactionStatus,
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
            actor=actor,
        )
    )


def execute_action(
    db: Session, action: ScheduledAction, run_type: str, actor: str, advance_schedule: bool = True
) -> ScheduledActionRun:
    schedule_key = action.execute_at.strftime("%Y%m%d%H%M")
    run_key = f"{action.id}:{schedule_key}:{run_type}"
    existing = db.scalar(select(ScheduledActionRun).where(ScheduledActionRun.run_key == run_key))
    if existing:
        return existing
    wallet_ids = target_wallet_ids(db, action)
    affected = 0
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
            history = db.scalar(select(func.count(MoneyTransaction.id)).where(MoneyTransaction.wallet_id == wallet.id))
            coupons = db.scalar(select(func.count(CouponInstance.id)).where(CouponInstance.wallet_id == wallet.id))
            if history or coupons:
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
        source = CouponStatus.available if action.action_type == ActionType.disable_coupons else CouponStatus.disabled
        target = CouponStatus.disabled if source == CouponStatus.available else CouponStatus.available
        coupons = list(
            db.scalars(
                select(CouponInstance)
                .where(CouponInstance.wallet_id.in_(wallet_ids), CouponInstance.status == source)
                .with_for_update()
            )
        )
        for coupon in coupons:
            coupon.status = target
            record_coupon_audit(db, coupon, target.value, actor)
        affected = len(coupons)
        message = f"Updated {affected} coupons."
    run = ScheduledActionRun(
        action_id=action.id,
        run_key=run_key,
        run_type=run_type,
        affected_count=affected,
        success=True,
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
