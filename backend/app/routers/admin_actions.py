from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..actions import execute_action
from ..database import get_db, utcnow
from ..dependencies import require_admin, require_admin_csrf
from ..errors import ApiError
from ..models import (
    ActionType,
    ActionWalletOverride,
    AdminUser,
    EmailTemplate,
    ScheduledAction,
    ScheduledActionRun,
    Wallet,
)
from ..schemas import ActionCreate, ActionWalletScope
from .admin_common import get_event

router = APIRouter()


@router.get("/events/{event_id}/actions")
def list_actions(
    event_id: int, _: AdminUser = Depends(require_admin), db: Session = Depends(get_db)
) -> dict:
    get_event(db, event_id)
    actions = list(
        db.scalars(
            select(ScheduledAction)
            .where(ScheduledAction.event_id == event_id)
            .order_by(ScheduledAction.execute_at.desc())
        )
    )
    run_counts: dict[int, int] = {
        action_id: count
        for action_id, count in db.execute(
            select(ScheduledActionRun.action_id, func.count(ScheduledActionRun.id))
            .where(ScheduledActionRun.action_id.in_([action.id for action in actions]))
            .group_by(ScheduledActionRun.action_id)
        )
    }
    runs = list(
        db.scalars(
            select(ScheduledActionRun)
            .join(ScheduledAction)
            .where(ScheduledAction.event_id == event_id)
            .order_by(ScheduledActionRun.executed_at.desc())
            .limit(50)
        )
    )
    return {
        "actions": [
            {
                "id": action.id,
                "name": action.name,
                "action_type": action.action_type,
                "email_template_id": action.email_template_id,
                "email_subject": action.email_subject,
                "schedule_type": action.schedule_type,
                "execute_at": action.execute_at,
                "schedule_start": action.schedule_start,
                "schedule_end": action.schedule_end,
                "schedule_time": action.schedule_time,
                "auto_delete": action.auto_delete,
                "enabled": action.enabled,
                "completed_at": action.completed_at,
                "run_count": run_counts.get(action.id, 0),
            }
            for action in actions
        ],
        "runs": [
            {
                "id": run.id,
                "action_id": run.action_id,
                "success": run.success,
                "affected_count": run.affected_count,
                "message": run.message,
                "executed_at": run.executed_at,
            }
            for run in runs
        ],
    }


@router.post("/events/{event_id}/actions", status_code=201)
def create_action(
    event_id: int,
    payload: ActionCreate,
    admin: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    get_event(db, event_id)
    validate_action_email_template(db, event_id, payload)
    action = ScheduledAction(
        event_id=event_id,
        name=payload.name,
        action_type=payload.action_type,
        schedule_type=payload.schedule_type,
        execute_at=payload.execute_at,
        schedule_start=payload.schedule_start or payload.execute_at.date(),
        schedule_end=payload.schedule_end,
        schedule_time=payload.schedule_time or payload.execute_at.time().replace(tzinfo=None),
        auto_delete=payload.auto_delete,
        email_template_id=payload.email_template_id,
        email_subject=payload.email_subject,
        created_by=f"admin:{admin.id}",
    )
    db.add(action)
    db.flush()
    for wallet_id in payload.excluded_wallet_ids:
        belongs = db.scalar(
            select(Wallet.id).where(Wallet.id == wallet_id, Wallet.event_id == event_id)
        )
        if belongs:
            db.add(ActionWalletOverride(action_id=action.id, wallet_id=wallet_id, included=False))
    db.commit()
    return {"action": {"id": action.id, "name": action.name}}


def validate_action_email_template(db: Session, event_id: int, payload: ActionCreate) -> None:
    if payload.action_type != ActionType.send_email:
        return
    template = db.scalar(
        select(EmailTemplate).where(
            EmailTemplate.id == payload.email_template_id,
            EmailTemplate.event_id == event_id,
            EmailTemplate.archived_at.is_(None),
        )
    )
    if not template:
        raise ApiError(
            422,
            "invalid_email_template",
            "Choose an active email template from this event.",
        )


@router.put("/events/{event_id}/actions/{action_id}")
def update_action(
    event_id: int,
    action_id: int,
    payload: ActionCreate,
    _: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    action = db.scalar(
        select(ScheduledAction)
        .where(ScheduledAction.id == action_id, ScheduledAction.event_id == event_id)
        .with_for_update()
    )
    if not action:
        raise ApiError(404, "not_found", "Scheduled action was not found.")
    validate_action_email_template(db, event_id, payload)
    action.name = payload.name
    action.action_type = payload.action_type
    action.schedule_type = payload.schedule_type
    action.execute_at = payload.execute_at
    action.schedule_start = payload.schedule_start or payload.execute_at.date()
    action.schedule_end = payload.schedule_end
    action.schedule_time = payload.schedule_time or payload.execute_at.time().replace(tzinfo=None)
    action.auto_delete = payload.auto_delete
    action.email_template_id = payload.email_template_id
    action.email_subject = payload.email_subject
    action.completed_at = None
    db.commit()
    return {"action": {"id": action.id, "name": action.name}}


@router.patch("/events/{event_id}/actions/{action_id}/enabled")
def set_action_enabled(
    event_id: int,
    action_id: int,
    enabled: bool,
    _: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    action = db.scalar(
        select(ScheduledAction)
        .where(ScheduledAction.id == action_id, ScheduledAction.event_id == event_id)
        .with_for_update()
    )
    if not action:
        raise ApiError(404, "not_found", "Scheduled action was not found.")
    action.enabled = enabled
    db.commit()
    return {"action": {"id": action.id, "enabled": action.enabled}}


@router.delete("/events/{event_id}/actions/{action_id}", status_code=204)
def delete_action(
    event_id: int,
    action_id: int,
    _: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> Response:
    action = db.scalar(
        select(ScheduledAction)
        .where(ScheduledAction.id == action_id, ScheduledAction.event_id == event_id)
        .with_for_update()
    )
    if not action:
        raise ApiError(404, "not_found", "Scheduled action was not found.")
    if db.scalar(
        select(func.count(ScheduledActionRun.id)).where(ScheduledActionRun.action_id == action.id)
    ):
        raise ApiError(
            409,
            "action_has_history",
            "Automations with execution history cannot be deleted. Disable the automation instead.",
        )
    db.delete(action)
    db.commit()
    return Response(status_code=204)


@router.post("/events/{event_id}/actions/{action_id}/run")
def run_action_now(
    event_id: int,
    action_id: int,
    admin: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    action = db.scalar(
        select(ScheduledAction)
        .where(ScheduledAction.id == action_id, ScheduledAction.event_id == event_id)
        .with_for_update()
    )
    if not action:
        raise ApiError(404, "not_found", "Scheduled action was not found.")
    # Manual runs are independently keyed and never consume the configured schedule.
    run = execute_action(
        db,
        action,
        f"manual-{utcnow().strftime('%Y%m%d%H%M%S%f')}",
        f"admin:{admin.id}",
        advance_schedule=False,
    )
    return {
        "run": {
            "id": run.id,
            "success": run.success,
            "affected_count": run.affected_count,
            "message": run.message,
        }
    }


@router.post("/events/{event_id}/actions/{action_id}/wallet-scope")
def apply_action_wallet_scope(
    event_id: int,
    action_id: int,
    payload: ActionWalletScope,
    admin: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    action = db.scalar(
        select(ScheduledAction)
        .where(ScheduledAction.id == action_id, ScheduledAction.event_id == event_id)
        .with_for_update()
    )
    if not action:
        raise ApiError(404, "not_found", "Scheduled action was not found.")

    requested_ids = list(dict.fromkeys(payload.wallet_ids))
    event_wallet_ids = set(
        db.scalars(
            select(Wallet.id).where(
                Wallet.event_id == event_id,
                Wallet.id.in_(requested_ids),
            )
        )
    )
    if len(event_wallet_ids) != len(requested_ids):
        raise ApiError(
            400,
            "invalid_wallet_scope",
            "One or more selected wallets do not belong to this event.",
        )

    if payload.operation == "execute":
        run = execute_action(
            db,
            action,
            f"scope-{utcnow().strftime('%Y%m%d%H%M%S%f')}",
            f"admin:{admin.id}",
            advance_schedule=False,
            wallet_ids_override=requested_ids,
        )
        return {
            "message": run.message,
            "affected_count": run.affected_count,
            "run_id": run.id,
        }

    included = payload.operation == "include"
    for wallet_id in requested_ids:
        override = db.get(ActionWalletOverride, (action.id, wallet_id))
        if override:
            override.included = included
        else:
            db.add(
                ActionWalletOverride(
                    action_id=action.id,
                    wallet_id=wallet_id,
                    included=included,
                )
            )
    db.commit()
    operation = "included in" if included else "excluded from"
    return {
        "message": f"{len(requested_ids)} wallets were {operation} the schedule.",
        "affected_count": len(requested_ids),
    }
