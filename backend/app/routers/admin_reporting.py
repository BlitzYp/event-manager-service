import csv
import io
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query, Response
from openpyxl import Workbook
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_admin
from ..errors import ApiError
from ..models import (
    AdminUser,
    CouponAudit,
    MoneyTransaction,
    TransactionStatus,
    TransactionType,
)
from .admin_common import get_event

router = APIRouter()


# Filtered financial ledger queries and participant/vendor snapshots.
@router.get("/events/{event_id}/transactions")
def transactions(
    event_id: int,
    status: TransactionStatus | None = None,
    transaction_type: TransactionType | None = Query(default=None, alias="type"),
    vendor_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str = "",
    _: AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Return up to 500 event ledger records matching the supplied filters."""
    get_event(db, event_id)
    query = transaction_query(
        event_id,
        status=status,
        transaction_type=transaction_type,
        vendor_id=vendor_id,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )
    rows = db.scalars(query.order_by(MoneyTransaction.created_at.desc()).limit(500))
    return {
        "transactions": [
            {
                "id": row.id,
                "reference": row.reference,
                "type": row.type,
                "status": row.status,
                "amount_minor": row.amount_minor,
                "participant_code": row.participant_code,
                "participant_name": row.participant_name,
                "group": row.group_name,
                "vendor_id": row.vendor_id,
                "vendor_name": row.vendor_name,
                "created_at": row.created_at,
            }
            for row in rows
        ]
    }


def transaction_query(
    event_id: int,
    *,
    status: TransactionStatus | None = None,
    transaction_type: TransactionType | None = None,
    vendor_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str = "",
):
    """Build an event-scoped ledger query without executing it, for listings and exports."""
    query = select(MoneyTransaction).where(MoneyTransaction.event_id == event_id)
    if status:
        query = query.where(MoneyTransaction.status == status)
    if transaction_type:
        query = query.where(MoneyTransaction.type == transaction_type)
    if vendor_id:
        query = query.where(MoneyTransaction.vendor_id == vendor_id)
    if date_from:
        query = query.where(MoneyTransaction.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        query = query.where(
            MoneyTransaction.created_at < datetime.combine(date_to + timedelta(days=1), time.min)
        )
    if search:
        term = f"%{search}%"
        query = query.where(
            or_(
                MoneyTransaction.participant_name.like(term),
                MoneyTransaction.participant_code.like(term),
                MoneyTransaction.group_name.like(term),
                MoneyTransaction.reference.like(term),
                MoneyTransaction.vendor_name.like(term),
            )
        )
    return query


# Coupon issuance, status, and redemption history.
@router.get("/events/{event_id}/coupon-audits")
def coupon_audits(
    event_id: int,
    vendor_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str = "",
    _: AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Return filtered event coupon history without modifying immutable audit records."""
    get_event(db, event_id)
    query = select(CouponAudit).where(CouponAudit.event_id == event_id)
    if vendor_id:
        query = query.where(CouponAudit.vendor_id == vendor_id)
    if date_from:
        query = query.where(CouponAudit.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        query = query.where(
            CouponAudit.created_at < datetime.combine(date_to + timedelta(days=1), time.min)
        )
    if search:
        term = f"%{search}%"
        query = query.where(
            or_(
                CouponAudit.participant_name.like(term),
                CouponAudit.participant_code.like(term),
                CouponAudit.reference.like(term),
                CouponAudit.coupon_name.like(term),
                CouponAudit.vendor_name.like(term),
            )
        )
    rows = db.scalars(query.order_by(CouponAudit.created_at.desc()).limit(500))
    return {
        "audits": [
            {
                "id": row.id,
                "reference": row.reference,
                "action": row.action,
                "coupon_name": row.coupon_name,
                "participant_code": row.participant_code,
                "participant_name": row.participant_name,
                "vendor_id": row.vendor_id,
                "vendor_name": row.vendor_name,
                "actor": row.actor,
                "created_at": row.created_at,
            }
            for row in rows
        ]
    }


# CSV/Excel export formatting; no ledger records are modified.
def ledger_rows(
    db: Session,
    event_id: int,
    *,
    status: TransactionStatus | None = None,
    transaction_type: TransactionType | None = None,
    vendor_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str = "",
) -> list[list]:
    """Convert transaction records to ordered spreadsheet/CSV cell values."""
    rows = db.scalars(
        transaction_query(
            event_id,
            status=status,
            transaction_type=transaction_type,
            vendor_id=vendor_id,
            date_from=date_from,
            date_to=date_to,
            search=search,
        ).order_by(MoneyTransaction.created_at.desc())
    )
    return [
        [
            row.reference,
            row.created_at.isoformat(),
            row.type.value,
            row.status.value,
            row.amount_minor,
            row.participant_code,
            row.participant_name,
            row.group_name or "",
            row.vendor_name or "",
            row.actor,
            row.note or "",
        ]
        for row in rows
    ]


@router.get("/events/{event_id}/transactions/export.{format}")
def export_transactions(
    event_id: int,
    format: str,
    status: TransactionStatus | None = None,
    transaction_type: TransactionType | None = Query(default=None, alias="type"),
    vendor_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str = "",
    _: AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    """Return the filtered event ledger as a downloadable CSV or Excel response."""
    event = get_event(db, event_id)
    if format not in {"csv", "xlsx"}:
        raise ApiError(404, "not_found", "Export format was not found.")
    headers = [
        "reference",
        "created_at",
        "type",
        "status",
        "amount_minor",
        "participant_code",
        "participant_name",
        "group",
        "vendor",
        "actor",
        "note",
    ]
    rows = ledger_rows(
        db,
        event_id,
        status=status,
        transaction_type=transaction_type,
        vendor_id=vendor_id,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )
    if format == "csv":
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        return Response(
            output.getvalue(),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{event.code}-transactions.csv"'
            },
        )
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Transactions"
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    binary = io.BytesIO()
    workbook.save(binary)
    return Response(
        binary.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{event.code}-transactions.xlsx"'},
    )
