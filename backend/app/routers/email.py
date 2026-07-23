from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import EmailAsset

router = APIRouter(tags=["email assets"])


@router.get("/email-assets/{asset_id}", include_in_schema=False)
def public_email_asset(
    asset_id: int,
    token: str = Query(min_length=20, max_length=100),
    db: Session = Depends(get_db),
) -> Response:
    asset = db.scalar(
        select(EmailAsset).where(
            EmailAsset.id == asset_id,
            EmailAsset.public_token == token,
        )
    )
    if not asset:
        return Response(status_code=404)
    return Response(
        content=asset.content,
        media_type=asset.mime_type,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )
