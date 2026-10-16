"""Super-admin account management and session impersonation."""

from fastapi import APIRouter, Cookie, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_admin, require_admin_csrf
from ..errors import ApiError
from ..models import AdminSession, AdminUser, Event
from ..schemas import AdminAccountStatusUpdate
from ..security import token_hash

router = APIRouter()


def require_super_admin(admin: AdminUser) -> None:
    """Raise a 403 error unless the supplied account is a super-admin."""
    if not admin.is_super_admin:
        raise ApiError(403, "super_admin_required", "Super-admin access is required.")


@router.get("/accounts")
def list_admin_accounts(
    admin: AdminUser = Depends(require_admin), db: Session = Depends(get_db)
) -> dict:
    """Return administrator accounts, their event counts, and account/event totals."""
    require_super_admin(admin)
    rows = db.execute(
        select(AdminUser, func.count(Event.id))
        .outerjoin(Event, Event.admin_id == AdminUser.id)
        .group_by(AdminUser.id)
        .order_by(AdminUser.created_at)
    ).all()
    return {
        "accounts": [
            {
                "id": account.id,
                "email": account.email,
                "is_active": account.is_active,
                "is_super_admin": account.is_super_admin,
                "event_count": event_count,
                "created_at": account.created_at,
            }
            for account, event_count in rows
        ],
        "totals": {
            "admins": len(rows),
            "events": sum(event_count for _, event_count in rows),
        },
    }


@router.post("/accounts/{account_id}/impersonate")
def impersonate_admin(
    account_id: int,
    admin: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
    admin_session: str | None = Cookie(default=None),
) -> dict:
    """Commit a session switch to an active regular admin and return that identity."""
    require_super_admin(admin)
    target = db.get(AdminUser, account_id)
    if not target or not target.is_active:
        raise ApiError(404, "not_found", "Active administrator account was not found.")
    if target.id == admin.id or target.is_super_admin:
        raise ApiError(409, "invalid_impersonation", "Select a regular administrator account.")
    session = db.scalar(
        select(AdminSession)
        .where(AdminSession.token_hash == token_hash(admin_session or ""))
        .with_for_update()
    )
    if not session:
        raise ApiError(401, "authentication_required", "Authentication required.")
    session.admin_id = target.id
    session.impersonator_admin_id = admin.id
    db.commit()
    return {"user": {"id": target.id, "email": target.email, "impersonating": True}}


@router.patch("/accounts/{account_id}/status")
def set_admin_account_status(
    account_id: int,
    payload: AdminAccountStatusUpdate,
    admin: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    """Commit account availability and session revocations; return the updated account."""
    require_super_admin(admin)
    target = db.scalar(select(AdminUser).where(AdminUser.id == account_id).with_for_update())
    if not target:
        raise ApiError(404, "not_found", "Administrator account was not found.")
    if target.id == admin.id or target.is_super_admin:
        raise ApiError(409, "protected_account", "Super-admin accounts cannot be disabled here.")
    target.is_active = payload.is_active
    db.commit()
    return {
        "account": {
            "id": target.id,
            "email": target.email,
            "is_active": target.is_active,
        }
    }
