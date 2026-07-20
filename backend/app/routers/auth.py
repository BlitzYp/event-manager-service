from datetime import timedelta

from fastapi import APIRouter, Cookie, Depends, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db, utcnow
from ..dependencies import (
    require_admin_csrf,
    require_admin_identity,
    require_admin_identity_csrf,
)
from ..errors import ApiError
from ..models import AdminSession, AdminUser
from ..schemas import AdminRegister, LoginRequest
from ..security import hash_password, new_token, token_hash, verify_password

router = APIRouter(prefix="/auth", tags=["admin-auth"])


def user_json(admin: AdminUser, impersonating: bool = False) -> dict:
    return {
        "id": admin.id,
        "email": admin.email,
        "is_super_admin": admin.is_super_admin,
        "is_active": admin.is_active,
        "impersonating": impersonating,
    }


@router.post("/register", status_code=201)
def register(payload: AdminRegister, response: Response, db: Session = Depends(get_db)) -> dict:
    admin = AdminUser(
        email=payload.email,
        password_hash=hash_password(payload.password),
        is_active=True,
        is_super_admin=False,
    )
    db.add(admin)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "email_exists", "An account with this email already exists.") from exc
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
    return {"user": user_json(admin), "csrf_token": raw_csrf}


@router.post("/login")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> dict:
    admin = db.scalar(select(AdminUser).where(AdminUser.email == payload.email.lower()))
    if (
        not admin or not verify_password(payload.password, admin.password_hash)
    ):
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
        "admin_session",
        raw_session,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.admin_session_hours * 3600,
        path="/",
    )
    return {"user": user_json(admin), "csrf_token": raw_csrf}


@router.get("/me")
def me(
    admin: AdminUser = Depends(require_admin_identity),
    db: Session = Depends(get_db),
    admin_session: str | None = Cookie(default=None),
) -> dict:
    session = db.scalar(
        select(AdminSession).where(AdminSession.token_hash == token_hash(admin_session or ""))
    )
    return {"user": user_json(admin, bool(session and session.impersonator_admin_id))}


@router.post("/stop-impersonating")
def stop_impersonating(
    admin: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
    admin_session: str | None = Cookie(default=None),
) -> dict:
    session = db.scalar(
        select(AdminSession)
        .where(AdminSession.token_hash == token_hash(admin_session or ""))
        .with_for_update()
    )
    if not session or not session.impersonator_admin_id:
        raise ApiError(409, "not_impersonating", "This session is not impersonating an account.")
    original = db.get(AdminUser, session.impersonator_admin_id)
    if not original or not original.is_active or not original.is_super_admin:
        raise ApiError(403, "impersonation_unavailable", "The super-admin account is unavailable.")
    session.admin_id = original.id
    session.impersonator_admin_id = None
    db.commit()
    return {"user": user_json(original), "csrf_token": "unchanged"}


@router.post("/csrf")
def csrf(
    admin: AdminUser = Depends(require_admin_identity),
    db: Session = Depends(get_db),
    admin_session: str | None = Cookie(default=None),
) -> dict:
    row = db.scalar(
        select(AdminSession).where(AdminSession.token_hash == token_hash(admin_session or ""))
    )
    if not row:
        raise ApiError(401, "authentication_required", "Authentication required.")
    raw = new_token()
    row.csrf_hash = token_hash(raw)
    db.commit()
    return {"csrf_token": raw}


@router.post("/logout")
def logout(
    response: Response,
    admin: AdminUser = Depends(require_admin_identity_csrf),
    db: Session = Depends(get_db),
    admin_session: str | None = Cookie(default=None),
) -> dict:
    row = db.scalar(
        select(AdminSession).where(AdminSession.token_hash == token_hash(admin_session or ""))
    )
    if row:
        row.revoked_at = utcnow()
        db.commit()
    response.delete_cookie("admin_session", path="/")
    return {"message": "Signed out."}
