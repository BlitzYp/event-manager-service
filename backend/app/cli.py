import argparse
import getpass
import os

from sqlalchemy import select

from .database import SessionLocal
from .models import AdminUser, Event, EventMode, EventStatus
from .schemas import normalize_admin_email
from .security import hash_password


def create_admin(email: str | None, password: str | None) -> None:
    raw_email = email or os.getenv("ADMIN_EMAIL") or input("Admin email: ")
    try:
        email = normalize_admin_email(raw_email)
    except ValueError as exc:
        raise SystemExit(f"Invalid admin email: {exc}") from exc
    password = password or os.getenv("ADMIN_PASSWORD") or getpass.getpass("Admin password: ")
    if len(password) < 8:
        raise SystemExit("Password must be at least 8 characters.")
    with SessionLocal() as db:
        admin = db.scalar(select(AdminUser).where(AdminUser.email == email))
        if admin:
            admin.password_hash = hash_password(password)
            admin.is_active = True
            admin.is_super_admin = True
            message = "Admin password updated."
        else:
            db.add(
                AdminUser(
                    email=email,
                    password_hash=hash_password(password),
                    is_super_admin=True,
                )
            )
            message = "Super-admin created."
        db.commit()
        print(message)


def seed_demo() -> None:
    if os.getenv("APP_ENV", "development") == "production":
        raise SystemExit("Demo data is disabled in production.")
    with SessionLocal() as db:
        if db.scalar(select(Event.id).where(Event.code == "demo")):
            print("Demo event already exists.")
            return
        db.add(
            Event(
                code="demo",
                name="Community Summer Event",
                status=EventStatus.active,
                mode=EventMode.both,
                currency="EUR",
                default_balance_minor=5000,
            )
        )
        db.commit()
        print("Demo event created. Add participants and vendors from the admin UI.")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    admin = subparsers.add_parser("create-admin")
    admin.add_argument("--email")
    admin.add_argument("--password")
    subparsers.add_parser("seed-demo")
    args = parser.parse_args()
    create_admin(args.email, args.password) if args.command == "create-admin" else seed_demo()


if __name__ == "__main__":
    main()
