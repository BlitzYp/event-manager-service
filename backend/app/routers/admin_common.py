from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import ApiError
from ..models import Event


def event_json(row: Event) -> dict:
    """Return the event settings exposed in administrator API responses."""
    return {
        "id": row.id,
        "code": row.code,
        "name": row.name,
        "status": row.status,
        "mode": row.mode,
        "currency": row.currency,
        "default_balance_minor": row.default_balance_minor,
        "qr_ttl_seconds": row.qr_ttl_seconds,
        "approval_required": row.approval_required,
        "pending_payment_minutes": row.pending_payment_minutes,
        "created_at": row.created_at,
    }


def get_event(db: Session, event_id: int, lock: bool = False) -> Event:
    """Return the requested event, optionally locked, or raise a not-found API error."""
    query = select(Event).where(Event.id == event_id)
    if lock:
        query = query.with_for_update()
    event = db.scalar(query)
    if not event:
        raise ApiError(404, "not_found", "Event was not found.")
    return event
