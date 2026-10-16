"""Atomic CSV participant import and one-time wallet-link export."""

import csv
import io

from fastapi import APIRouter, Depends, File, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..dependencies import require_admin_csrf
from ..errors import ApiError
from ..models import AdminUser, Participant
from ..services import (
    create_participant_with_wallet,
    event_supports,
    issue_coupons,
    validate_participant_csv,
)
from .admin_common import get_event

router = APIRouter()


@router.post("/events/{event_id}/participants/import")
async def import_participants(
    event_id: int,
    file: UploadFile = File(...),
    admin: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> Response:
    """Commit an entire validated CSV or roll it back; return a CSV of secret wallet links."""
    event = get_event(db, event_id)
    content = await file.read()
    if len(content) > 5_000_000:
        raise ApiError(413, "file_too_large", "CSV file is too large.")
    rows = validate_participant_csv(content)
    codes = [str(row["participant_code"]) for row in rows]
    existing = set(
        db.scalars(
            select(Participant.participant_code).where(
                Participant.event_id == event_id, Participant.participant_code.in_(codes)
            )
        )
    )
    if existing:
        raise ApiError(
            409,
            "participant_code_exists",
            f"Codes already exist: {', '.join(sorted(existing)[:20])}",
        )
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["participant_code", "name", "group", "email", "wallet_link"])
    try:
        for row in rows:
            participant, wallet, raw = create_participant_with_wallet(
                db,
                event,
                str(row["participant_code"]),
                str(row["name"]),
                str(row["group"]) if row["group"] else None,
                str(row["email"]) if row["email"] else None,
            )
            if event_supports(event, "coupons"):
                issue_coupons(db, event.id, [wallet.id], f"admin:{admin.id}")
            writer.writerow(
                [
                    participant.participant_code,
                    participant.name,
                    participant.group_name or "",
                    participant.email or "",
                    f"{settings.public_app_url}/wallet/{raw}",
                ]
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return Response(
        output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{event.code}-wallet-links.csv"',
            "Cache-Control": "no-store",
        },
    )
