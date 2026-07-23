import io
import json

from fastapi import APIRouter, Depends, File, Response, UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db, utcnow
from ..dependencies import require_admin, require_admin_csrf, require_admin_event_access
from ..email_service import send_template_email, validate_template_document
from ..errors import ApiError
from ..models import (
    AdminUser,
    EmailAsset,
    EmailDelivery,
    EmailDeliveryStatus,
    EmailTemplate,
    Event,
    Participant,
)
from ..schemas import (
    EmailSendRequest,
    EmailTemplateArchive,
    EmailTemplateCreate,
    EmailTemplateUpdate,
)
from ..security import new_token

router = APIRouter(
    prefix="/admin",
    tags=["email administration"],
    dependencies=[Depends(require_admin_event_access)],
)


def get_event(db: Session, event_id: int) -> Event:
    event = db.scalar(select(Event).where(Event.id == event_id))
    if not event:
        raise ApiError(404, "not_found", "Event was not found.")
    return event


def template_json(row: EmailTemplate, include_content: bool = False) -> dict:
    result = {
        "id": row.id,
        "event_id": row.event_id,
        "name": row.name,
        "subject": row.subject,
        "version": row.version,
        "archived_at": row.archived_at,
        "created_by": row.created_by,
        "updated_by": row.updated_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
    if include_content:
        result["document"] = json.loads(row.document_json)
        result["rendered_html"] = row.rendered_html
    return result


def ensure_name_available(
    db: Session, event_id: int, name: str, template_id: int | None = None
) -> None:
    duplicate = db.scalar(
        select(EmailTemplate.id).where(
            EmailTemplate.event_id == event_id,
            EmailTemplate.name == name,
            EmailTemplate.archived_at.is_(None),
            EmailTemplate.id != (template_id or 0),
        )
    )
    if duplicate:
        raise ApiError(
            409,
            "email_template_name_exists",
            "An active email template with this name already exists.",
        )


@router.get("/events/{event_id}/email-templates")
def list_templates(
    event_id: int,
    include_archived: bool = False,
    _: AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    get_event(db, event_id)
    query = select(EmailTemplate).where(EmailTemplate.event_id == event_id)
    if not include_archived:
        query = query.where(EmailTemplate.archived_at.is_(None))
    rows = db.scalars(query.order_by(EmailTemplate.archived_at, EmailTemplate.name))
    return {"templates": [template_json(row) for row in rows]}


@router.get("/events/{event_id}/email-templates/{template_id}")
def get_template(
    event_id: int,
    template_id: int,
    _: AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    row = db.scalar(
        select(EmailTemplate).where(
            EmailTemplate.id == template_id,
            EmailTemplate.event_id == event_id,
        )
    )
    if not row:
        raise ApiError(404, "not_found", "Email template was not found.")
    return {"template": template_json(row, include_content=True)}


@router.post("/events/{event_id}/email-templates", status_code=201)
def create_template(
    event_id: int,
    payload: EmailTemplateCreate,
    admin: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    get_event(db, event_id)
    name = payload.name.strip()
    ensure_name_available(db, event_id, name)
    document_json = validate_template_document(
        db, event_id, payload.document, payload.rendered_html
    )
    actor = f"admin:{admin.id}"
    row = EmailTemplate(
        event_id=event_id,
        name=name,
        subject=payload.subject.strip(),
        document_json=document_json,
        rendered_html=payload.rendered_html.strip(),
        version=1,
        created_by=actor,
        updated_by=actor,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"template": template_json(row, include_content=True)}


@router.put("/events/{event_id}/email-templates/{template_id}")
def update_template(
    event_id: int,
    template_id: int,
    payload: EmailTemplateUpdate,
    admin: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    row = db.scalar(
        select(EmailTemplate)
        .where(
            EmailTemplate.id == template_id,
            EmailTemplate.event_id == event_id,
        )
        .with_for_update()
    )
    if not row:
        raise ApiError(404, "not_found", "Email template was not found.")
    if row.version != payload.version:
        raise ApiError(
            409,
            "email_template_conflict",
            "This template was changed by another administrator. Reload it and try again.",
        )
    name = payload.name.strip()
    ensure_name_available(db, event_id, name, template_id)
    row.document_json = validate_template_document(
        db, event_id, payload.document, payload.rendered_html
    )
    row.name = name
    row.subject = payload.subject.strip()
    row.rendered_html = payload.rendered_html.strip()
    row.version += 1
    row.updated_by = f"admin:{admin.id}"
    db.commit()
    return {"template": template_json(row, include_content=True)}


@router.patch("/events/{event_id}/email-templates/{template_id}/archive")
def archive_template(
    event_id: int,
    template_id: int,
    payload: EmailTemplateArchive,
    admin: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    row = db.scalar(
        select(EmailTemplate)
        .where(
            EmailTemplate.id == template_id,
            EmailTemplate.event_id == event_id,
        )
        .with_for_update()
    )
    if not row:
        raise ApiError(404, "not_found", "Email template was not found.")
    if not payload.archived:
        ensure_name_available(db, event_id, row.name, row.id)
    row.archived_at = utcnow() if payload.archived else None
    row.archived_by = f"admin:{admin.id}" if payload.archived else None
    row.updated_by = f"admin:{admin.id}"
    db.commit()
    return {"template": template_json(row)}


def asset_json(row: EmailAsset) -> dict:
    return {
        "id": row.id,
        "original_name": row.original_name,
        "mime_type": row.mime_type,
        "file_size": row.file_size,
        "width": row.width,
        "height": row.height,
        "created_at": row.created_at,
        "url": (
            f"{settings.public_app_url.rstrip('/')}/api/v1/email-assets/{row.id}"
            f"?token={row.public_token}"
        ),
    }


@router.get("/events/{event_id}/email-assets")
def list_assets(
    event_id: int,
    _: AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    get_event(db, event_id)
    rows = db.scalars(
        select(EmailAsset)
        .where(EmailAsset.event_id == event_id)
        .order_by(EmailAsset.created_at.desc())
    )
    return {"assets": [asset_json(row) for row in rows]}


@router.post("/events/{event_id}/email-assets", status_code=201)
def upload_asset(
    event_id: int,
    file: UploadFile = File(...),
    admin: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    get_event(db, event_id)
    content = file.file.read(5_242_881)
    if not content or len(content) > 5_242_880:
        raise ApiError(422, "invalid_image", "Image size must be between 1 byte and 5 MB.")
    allowed_formats = {
        "JPEG": "image/jpeg",
        "PNG": "image/png",
        "GIF": "image/gif",
        "WEBP": "image/webp",
    }
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            width, height = image.size
            mime_type = allowed_formats.get(image.format or "")
    except (UnidentifiedImageError, OSError):
        mime_type = None
        width = height = 0
    if not mime_type or not (0 < width <= 10_000 and 0 < height <= 10_000):
        raise ApiError(
            422,
            "invalid_image",
            "Only valid JPEG, PNG, GIF, and WebP images are allowed.",
        )
    row = EmailAsset(
        event_id=event_id,
        public_token=new_token(32),
        original_name=(file.filename or "image")[:255],
        mime_type=mime_type,
        file_size=len(content),
        width=width,
        height=height,
        content=content,
        uploaded_by=f"admin:{admin.id}",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"asset": asset_json(row)}


@router.delete("/events/{event_id}/email-assets/{asset_id}", status_code=204)
def delete_asset(
    event_id: int,
    asset_id: int,
    _: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> Response:
    row = db.scalar(
        select(EmailAsset).where(
            EmailAsset.id == asset_id,
            EmailAsset.event_id == event_id,
        )
    )
    if not row:
        raise ApiError(404, "not_found", "Email image was not found.")
    url_fragment = f"/api/v1/email-assets/{row.id}?token={row.public_token}"
    in_use = db.scalar(
        select(EmailTemplate.id).where(
            EmailTemplate.event_id == event_id,
            or_(
                EmailTemplate.document_json.contains(url_fragment),
                EmailTemplate.rendered_html.contains(url_fragment),
            ),
        )
    )
    if in_use:
        raise ApiError(
            409,
            "email_asset_in_use",
            "This image is used by an email template and cannot be deleted.",
        )
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@router.post("/events/{event_id}/emails/send")
def send_email(
    event_id: int,
    payload: EmailSendRequest,
    admin: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
) -> dict:
    event = get_event(db, event_id)
    template = None
    if payload.source == "template":
        template = db.scalar(
            select(EmailTemplate).where(
                EmailTemplate.id == payload.template_id,
                EmailTemplate.event_id == event_id,
                EmailTemplate.archived_at.is_(None),
            )
        )
        if not template:
            raise ApiError(404, "not_found", "Email template was not found.")

    participants: list[Participant] = []
    if payload.participant_ids or payload.all_participants or payload.group is not None:
        query = select(Participant).where(Participant.event_id == event_id)
        if payload.participant_ids:
            query = query.where(Participant.id.in_(payload.participant_ids))
        elif payload.group is not None:
            query = query.where(Participant.group_name == payload.group)
        participants = list(db.scalars(query.order_by(Participant.name).limit(1_001)))
        if len(participants) > 1_000:
            raise ApiError(
                422,
                "too_many_recipients",
                "A bulk send is limited to 1,000 recipients.",
            )
        if payload.participant_ids and len(participants) != len(set(payload.participant_ids)):
            raise ApiError(422, "invalid_recipients", "One or more participants were not found.")

    deliveries: list[EmailDelivery] = []
    skipped = 0
    delivery_number = 0
    for participant in participants:
        if not participant.email:
            skipped += 1
            continue
        deliveries.append(
            send_template_email(
                db,
                event=event,
                template=template,
                participant=participant,
                actor=f"admin:{admin.id}",
                subject_override=payload.subject,
                basic_body=payload.body,
                development_delivery_number=delivery_number,
            )
        )
        delivery_number += 1
    if payload.recipient_email:
        deliveries.append(
            send_template_email(
                db,
                event=event,
                template=template,
                recipient_email=str(payload.recipient_email),
                recipient_name=payload.recipient_name,
                actor=f"admin:{admin.id}",
                subject_override=payload.subject,
                basic_body=payload.body,
            )
        )
    db.commit()
    counts = {
        status.value: sum(delivery.status == status for delivery in deliveries)
        for status in EmailDeliveryStatus
    }
    return {
        **counts,
        "skipped": skipped,
        "total": len(deliveries) + skipped,
        "development_mode": settings.environment.lower() != "production",
    }


@router.get("/events/{event_id}/email-deliveries")
def list_deliveries(
    event_id: int,
    _: AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    get_event(db, event_id)
    rows = db.scalars(
        select(EmailDelivery)
        .where(EmailDelivery.event_id == event_id)
        .order_by(EmailDelivery.created_at.desc())
        .limit(500)
    )
    return {
        "deliveries": [
            {
                "id": row.id,
                "template_id": row.template_id,
                "participant_id": row.participant_id,
                "recipient_email": row.recipient_email,
                "recipient_name": row.recipient_name,
                "subject": row.subject,
                "status": row.status,
                "error": row.error,
                "created_at": row.created_at,
                "sent_at": row.sent_at,
            }
            for row in rows
        ],
        "development_mode": settings.environment.lower() != "production",
        "test_recipient": (
            settings.email_test_recipient
            if settings.environment.lower() != "production"
            else None
        ),
        "development_delivery_limit": settings.development_email_delivery_limit,
    }
