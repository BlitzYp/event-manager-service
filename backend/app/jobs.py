import sys
import time

from sqlalchemy import select, text

from .actions import execute_action, expire_pending_payments
from .database import SessionLocal, utcnow
from .models import ScheduledAction


def run_due() -> dict[str, int]:
    with SessionLocal() as db:
        acquired = db.scalar(text("SELECT GET_LOCK('event-manager-scheduler', 0)"))
        if acquired != 1:
            return {"actions": 0, "expired_payments": 0}
        try:
            expired = expire_pending_payments(db)
            action_ids = list(
                db.scalars(
                    select(ScheduledAction.id).where(
                        ScheduledAction.enabled.is_(True),
                        ScheduledAction.completed_at.is_(None),
                        ScheduledAction.execute_at <= utcnow(),
                    ).order_by(ScheduledAction.execute_at, ScheduledAction.id)
                )
            )
            executed = 0
            for action_id in action_ids:
                action = db.scalar(select(ScheduledAction).where(ScheduledAction.id == action_id).with_for_update())
                if action and action.enabled and action.execute_at <= utcnow():
                    execute_action(db, action, "scheduled", "system:scheduler")
                    executed += 1
            return {"actions": executed, "expired_payments": expired}
        finally:
            db.execute(text("SELECT RELEASE_LOCK('event-manager-scheduler')"))
            db.commit()


def loop() -> None:
    while True:
        try:
            print(run_due(), flush=True)
        except Exception as exc:  # scheduler must survive transient database failures
            print(f"scheduler error: {type(exc).__name__}", file=sys.stderr, flush=True)
        time.sleep(60)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "loop":
        loop()
    else:
        print(run_due())

