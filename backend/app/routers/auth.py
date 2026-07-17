from datetime import timedelta

from fastapi import APIRouter, Cookie, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db, utcnow
from ..dependencies import require_admin, require_admin_csrf
from ..errors import ApiError
from ..models import AdminSession, AdminUser
from ..schemas import LoginRequest
from ..security import new_token, token_hash, verify_password

router = APIRouter(prefix="/auth", tags=["admin-auth"])


@router.post("/login")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> dict:
    admin = db.scalar(select(AdminUser).where(AdminUser.email == payload.email.lower()))
    if not admin or not admin.is_active or not verify_password(payload.password, admin.password_hash):
        raise ApiError(401, "invalid_credentials", "Email or password is incorrect.")
    raw_session, raw_csrf = new_token(), new_token()
    db.add(
        AdminSession(
            admin_id=admin.id,
            token_hash=token_hash(raw_session),
            csrf_hash=token_hash(raw_csrf),
            expires_at=utcnow() + timedelta(hours=settings.admin_session_hours),
        )
    )
    db.commit()
    response.set_cookie(
        "admin_session", raw_session, httponly=True, secure=settings.cookie_secure,
        samesite="lax", max_age=settings.admin_session_hours * 3600, path="/",
    )
    return {"user": {"id": admin.id, "email": admin.email}, "csrf_token": raw_csrf}


@router.get("/me")
def me(admin: AdminUser = Depends(require_admin)) -> dict:
    return {"user": {"id": admin.id, "email": admin.email}}


@router.post("/csrf")
def csrf(
    admin: AdminUser = Depends(require_admin), db: Session = Depends(get_db),
    admin_session: str | None = Cookie(default=None),
) -> dict:
    row = db.scalar(select(AdminSession).where(AdminSession.token_hash == token_hash(admin_session or "")))
    if not row:
        raise ApiError(401, "authentication_required", "Authentication required.")
    raw = new_token()
    row.csrf_hash = token_hash(raw)
    db.commit()
    return {"csrf_token": raw}


@router.post("/logout")
def logout(
    response: Response,
    admin: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
    admin_session: str | None = Cookie(default=None),
) -> dict:
    row = db.scalar(select(AdminSession).where(AdminSession.token_hash == token_hash(admin_session or "")))
    if row:
        row.revoked_at = utcnow()
        db.commit()
    response.delete_cookie("admin_session", path="/")
    return {"message": "Signed out."}
