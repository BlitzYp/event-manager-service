from datetime import timedelta

from fastapi import Cookie, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db, utcnow
from .errors import ApiError
from .models import AdminSession, AdminUser, Event, EventStatus, Vendor, VendorSession
from .security import safe_equal_hash, token_hash


# Administrator session identity, account status, and CSRF checks.
def require_admin_identity(
    db: Session = Depends(get_db), admin_session: str | None = Cookie(default=None)
) -> AdminUser:
    """Return the administrator behind a live locked session, or raise an authentication error."""
    if not admin_session:
        raise ApiError(401, "authentication_required", "Authentication required.")
    row = db.scalar(
        select(AdminSession)
        .where(
            AdminSession.token_hash == token_hash(admin_session),
            AdminSession.revoked_at.is_(None),
            AdminSession.expires_at > utcnow(),
        )
        .with_for_update()
    )
    if not row:
        raise ApiError(401, "authentication_required", "Authentication required.")
    return row.admin


def require_admin(admin: AdminUser = Depends(require_admin_identity)) -> AdminUser:
    """Return an authenticated active administrator or reject a disabled account."""
    if not admin.is_active:
        raise ApiError(403, "account_disabled", "This administrator account is disabled.")
    return admin


def require_admin_csrf(
    admin: AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
    admin_session: str | None = Cookie(default=None),
    x_csrf_token: str | None = Header(default=None),
) -> AdminUser:
    """Return the active administrator only after validating the session CSRF token."""
    session = db.scalar(
        select(AdminSession).where(AdminSession.token_hash == token_hash(admin_session or ""))
    )
    if not session or not x_csrf_token or not safe_equal_hash(x_csrf_token, session.csrf_hash):
        raise ApiError(403, "csrf_failed", "Security check failed.")
    return admin


def require_admin_identity_csrf(
    admin: AdminUser = Depends(require_admin_identity),
    db: Session = Depends(get_db),
    admin_session: str | None = Cookie(default=None),
    x_csrf_token: str | None = Header(default=None),
) -> AdminUser:
    """Validate session CSRF and return its identity, even if the account is disabled."""
    session = db.scalar(
        select(AdminSession).where(AdminSession.token_hash == token_hash(admin_session or ""))
    )
    if not session or not x_csrf_token or not safe_equal_hash(x_csrf_token, session.csrf_hash):
        raise ApiError(403, "csrf_failed", "Security check failed.")
    return admin


# Event ownership guard inherited by every administrator event route.
def require_admin_event_access(
    request: Request,
    admin: AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminUser:
    """Protect every /admin/events/{event_id}/... route from cross-account access."""
    raw_event_id = request.path_params.get("event_id")
    if raw_event_id is None or admin.is_super_admin:
        return admin
    event = db.scalar(
        select(Event.id).where(Event.id == int(raw_event_id), Event.admin_id == admin.id)
    )
    if not event:
        raise ApiError(404, "not_found", "Event was not found.")
    return admin


# Vendor idle-session checks, event availability, and CSRF validation.
def require_vendor(
    db: Session = Depends(get_db), vendor_session: str | None = Cookie(default=None)
) -> Vendor:
    """Validate vendor session, activity, and event status; commit activity refresh and return
    vendor.
    """
    if not vendor_session:
        raise ApiError(401, "authentication_required", "Authentication required.")
    cutoff = utcnow() - timedelta(minutes=settings.vendor_session_idle_minutes)
    session = db.scalar(
        select(VendorSession)
        .where(
            VendorSession.token_hash == token_hash(vendor_session),
            VendorSession.revoked_at.is_(None),
            VendorSession.last_activity_at > cutoff,
        )
        .with_for_update()
    )
    if (
        not session
        or not session.vendor.active
        or session.vendor.event.status != EventStatus.active
    ):
        raise ApiError(401, "authentication_required", "Authentication required.")
    session.last_activity_at = utcnow()
    db.commit()
    return session.vendor


def require_vendor_csrf(
    vendor: Vendor = Depends(require_vendor),
    db: Session = Depends(get_db),
    vendor_session: str | None = Cookie(default=None),
    x_csrf_token: str | None = Header(default=None),
) -> Vendor:
    """Return the authenticated vendor only after validating the session CSRF token."""
    session = db.scalar(
        select(VendorSession).where(VendorSession.token_hash == token_hash(vendor_session or ""))
    )
    if not session or not x_csrf_token or not safe_equal_hash(x_csrf_token, session.csrf_hash):
        raise ApiError(403, "csrf_failed", "Security check failed.")
    return vendor
