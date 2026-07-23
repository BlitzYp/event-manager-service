from __future__ import annotations

import html
import json
import re
import smtplib
from email.message import EmailMessage
from email.utils import formataddr
from html.parser import HTMLParser
from typing import Any
from urllib.parse import unquote, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .database import utcnow
from .errors import ApiError
from .models import (
    EmailAsset,
    EmailDelivery,
    EmailDeliveryStatus,
    EmailTemplate,
    Event,
    Participant,
    WalletAccessToken,
)
from .security import new_token, token_hash

DOCUMENT_MAX_BYTES = 1_048_576
HTML_MAX_BYTES = 2_097_152
SUPPORTED_BLOCK_TYPES = {
    "Avatar",
    "Button",
    "ColumnsContainer",
    "Container",
    "Divider",
    "EmailLayout",
    "Heading",
    "Html",
    "Image",
    "Spacer",
    "Text",
}
PLACEHOLDERS = {
    "{{participant_name}}",
    "{{participant_first_name}}",
    "{{participant_last_name}}",
    "{{participant_code}}",
    "{{participant_email}}",
    "{{participant_group}}",
    "{{event_name}}",
    "{{event_code}}",
    "{{wallet_link}}",
    "{{public_wallet}}",
}
ASSET_URL_RE = re.compile(r"/api/v1/email-assets/(\d+)\?token=([A-Za-z0-9_-]{20,100})")
HTML_URL_RE = re.compile(r"""(?:src|href)\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
SAFE_TEXT_COLOR_RE = re.compile(
    r"^(?:#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?|"
    r"rgba?\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}"
    r"(?:\s*,\s*(?:0(?:\.\d+)?|1(?:\.0+)?))?\s*\))$"
)


def validate_template_document(
    db: Session, event_id: int, document: dict[str, Any], rendered_html: str
) -> str:
    encoded = json.dumps(document, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode()) > DOCUMENT_MAX_BYTES:
        raise ApiError(422, "template_too_large", "Email template document is too large.")
    if len(rendered_html.encode()) > HTML_MAX_BYTES:
        raise ApiError(422, "template_too_large", "Rendered email HTML is too large.")
    root = document.get("root")
    if not isinstance(root, dict) or root.get("type") != "EmailLayout":
        raise ApiError(422, "invalid_template", "Email template must have an EmailLayout root.")

    for block_id, block in document.items():
        if not isinstance(block_id, str) or not isinstance(block, dict):
            raise ApiError(422, "invalid_template", "Email template contains an invalid block.")
        if block.get("type") not in SUPPORTED_BLOCK_TYPES:
            raise ApiError(422, "invalid_template", "Email template contains an unsupported block.")
        for child_id in _child_ids(block):
            if not isinstance(child_id, str) or child_id not in document:
                raise ApiError(
                    422,
                    "invalid_template",
                    "Email template contains a broken block link.",
                )
        for url in _block_urls(block):
            _validate_url(db, event_id, url)

    lowered = rendered_html.lower()
    if (
        "<script" in lowered
        or "javascript:" in lowered
        or re.search(r"\son[a-z]+\s*=", lowered)
    ):
        raise ApiError(422, "unsafe_template", "Rendered email HTML contains unsafe content.")
    for url in HTML_URL_RE.findall(rendered_html):
        _validate_url(db, event_id, html.unescape(url))
    _validate_managed_assets(db, event_id, rendered_html)
    return encoded


def _child_ids(block: dict[str, Any]) -> list[Any]:
    raw_data = block.get("data")
    data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
    raw_props = data.get("props")
    props: dict[str, Any] = raw_props if isinstance(raw_props, dict) else {}
    result = list(props.get("childrenIds") or [])
    for column in props.get("columns") or []:
        if isinstance(column, dict):
            result.extend(column.get("childrenIds") or [])
    if block.get("type") == "EmailLayout":
        result.extend(data.get("childrenIds") or [])
    return result


def _block_urls(block: dict[str, Any]) -> list[str]:
    raw_data = block.get("data")
    data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
    raw_props = data.get("props")
    props: dict[str, Any] = raw_props if isinstance(raw_props, dict) else {}
    if block.get("type") == "Button":
        return [str(props.get("url") or "")]
    if block.get("type") == "Image":
        return [str(props.get("url") or ""), str(props.get("linkHref") or "")]
    return []


def _validate_url(db: Session, event_id: int, value: str) -> None:
    if not value or unquote(html.unescape(value)) in {
        "{{wallet_link}}",
        "{{public_wallet}}",
    }:
        return
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise ApiError(422, "invalid_template_url", "Template links must use HTTP or HTTPS.")
    if "/api/v1/email-assets/" in parsed.path:
        public = urlparse(settings.public_app_url)
        if (
            parsed.scheme.lower() != public.scheme.lower()
            or parsed.hostname != public.hostname
            or parsed.port != public.port
        ):
            raise ApiError(
                422,
                "invalid_email_asset",
                "Managed email images must use this application's public URL.",
            )
        _validate_managed_assets(db, event_id, value)


def _validate_managed_assets(db: Session, event_id: int, value: str) -> None:
    matches = list(ASSET_URL_RE.finditer(value))
    if "/api/v1/email-assets/" in value and not matches:
        raise ApiError(422, "invalid_email_asset", "The template contains an invalid image URL.")
    for match in matches:
        asset = db.scalar(
            select(EmailAsset).where(
                EmailAsset.id == int(match.group(1)),
                EmailAsset.public_token == match.group(2),
                EmailAsset.event_id == event_id,
            )
        )
        if not asset:
            raise ApiError(
                422,
                "invalid_email_asset",
                "The template contains an image that does not belong to this event.",
            )


def template_values(
    event: Event,
    participant: Participant | None,
    recipient_email: str,
    recipient_name: str | None,
    wallet_link: str,
) -> dict[str, str]:
    full_name = participant.name if participant else (recipient_name or "")
    names = full_name.strip().split(maxsplit=1)
    return {
        "{{participant_name}}": full_name,
        "{{participant_first_name}}": names[0] if names else "",
        "{{participant_last_name}}": names[1] if len(names) > 1 else "",
        "{{participant_code}}": participant.participant_code if participant else "",
        "{{participant_email}}": recipient_email,
        "{{participant_group}}": (participant.group_name or "") if participant else "",
        "{{event_name}}": event.name,
        "{{event_code}}": event.code,
        "{{wallet_link}}": wallet_link,
        "{{public_wallet}}": wallet_link,
    }


def render_template(source: str, values: dict[str, str], *, escape_values: bool) -> str:
    rendered = source
    for placeholder, value in values.items():
        replacement = html.escape(value, quote=True) if escape_values else value
        rendered = rendered.replace(placeholder, replacement)
        if placeholder in {"{{wallet_link}}", "{{public_wallet}}"}:
            encoded = placeholder.removeprefix("{{").removesuffix("}}")
            rendered = rendered.replace(f"%7B%7B{encoded}%7D%7D", replacement)
    return rendered


class _BasicEmailSanitizer(HTMLParser):
    allowed_tags = {"a", "b", "strong", "i", "em", "u", "span", "p", "div", "br"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.open_tags: list[str] = []
        self.blocked_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style"}:
            self.blocked_depth += 1
            return
        if self.blocked_depth:
            return
        attributes = dict(attrs)
        if tag == "font":
            color = (attributes.get("color") or "").strip()
            if SAFE_TEXT_COLOR_RE.fullmatch(color):
                self.parts.append(f'<span style="color:{html.escape(color, quote=True)}">')
                self.open_tags.append("span")
            return
        if tag not in self.allowed_tags:
            return
        if tag == "br":
            self.parts.append("<br>")
            return
        if tag == "a":
            href = unquote(html.unescape(attributes.get("href") or ""))
            if href not in {"{{wallet_link}}", "{{public_wallet}}"}:
                return
            self.parts.append(f'<a href="{href}">')
        elif tag == "span":
            color_match = re.search(
                r"(?:^|;)\s*color\s*:\s*([^;]+)",
                attributes.get("style") or "",
                re.IGNORECASE,
            )
            color = color_match.group(1).strip() if color_match else ""
            if SAFE_TEXT_COLOR_RE.fullmatch(color):
                self.parts.append(f'<span style="color:{html.escape(color, quote=True)}">')
            else:
                self.parts.append("<span>")
        else:
            self.parts.append(f"<{tag}>")
        self.open_tags.append(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style"}:
            self.blocked_depth = max(0, self.blocked_depth - 1)
            return
        if self.blocked_depth or tag == "br":
            return
        expected = "span" if tag == "font" else tag
        if expected in self.open_tags:
            while self.open_tags:
                opened = self.open_tags.pop()
                self.parts.append(f"</{opened}>")
                if opened == expected:
                    break

    def handle_data(self, data: str) -> None:
        if not self.blocked_depth:
            self.parts.append(html.escape(data))

    def sanitized(self) -> str:
        while self.open_tags:
            self.parts.append(f"</{self.open_tags.pop()}>")
        return "".join(self.parts)


def basic_email_html(source: str) -> str:
    sanitizer = _BasicEmailSanitizer()
    sanitizer.feed(source.strip())
    sanitizer.close()
    escaped = sanitizer.sanitized()
    for placeholder in ("{{wallet_link}}", "{{public_wallet}}"):
        escaped = re.sub(
            rf'(?<!href="){re.escape(placeholder)}',
            f'<a href="{placeholder}">Open public wallet</a>',
            escaped,
        )
    return (
        '<div style="font-family:Arial,sans-serif;font-size:16px;line-height:1.6;'
        f'color:#1f2937;white-space:pre-wrap">{escaped}</div>'
    )


def create_email_wallet_link(db: Session, participant: Participant) -> str:
    raw_token = new_token()
    db.add(
        WalletAccessToken(
            wallet_id=participant.wallet.id,
            token_hash=token_hash(raw_token),
            expires_at=None,
        )
    )
    return f"{settings.public_app_url.rstrip('/')}/wallet/{raw_token}"


def send_template_email(
    db: Session,
    *,
    event: Event,
    template: EmailTemplate | None,
    actor: str,
    participant: Participant | None = None,
    recipient_email: str | None = None,
    recipient_name: str | None = None,
    subject_override: str | None = None,
    basic_body: str | None = None,
    development_delivery_number: int = 0,
) -> EmailDelivery:
    address = str(participant.email if participant else recipient_email or "")
    name = participant.name if participant else recipient_name
    is_development = settings.environment.lower() != "production"
    test_recipient = (settings.email_test_recipient or "").strip()
    will_deliver = not is_development or (
        bool(test_recipient)
        and development_delivery_number < settings.development_email_delivery_limit
    )
    public_url = urlparse(settings.public_app_url)
    asset_error = None
    body_source = template.rendered_html if template else basic_email_html(basic_body or "")
    if will_deliver and "/api/v1/email-assets/" in body_source:
        if public_url.scheme != "https" or (public_url.hostname or "").lower() in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            asset_error = (
                "Templates with uploaded images require PUBLIC_APP_URL to be a public HTTPS URL."
            )
    wallet_link = (
        create_email_wallet_link(db, participant)
        if participant is not None and will_deliver and not asset_error
        else "#"
    )
    values = template_values(event, participant, address, name, wallet_link)
    subject = render_template(
        subject_override or (template.subject if template else ""),
        values,
        escape_values=False,
    )
    body = render_template(body_source, values, escape_values=True)
    actual_recipient = test_recipient if is_development and test_recipient else address
    delivery = EmailDelivery(
        event_id=event.id,
        template_id=template.id if template else None,
        participant_id=participant.id if participant else None,
        recipient_email=address,
        recipient_name=name,
        subject=subject,
        status=EmailDeliveryStatus.simulated,
        error=None,
        created_by=actor,
    )
    db.add(delivery)

    if not will_deliver:
        return delivery
    if asset_error:
        delivery.status = EmailDeliveryStatus.failed
        delivery.error = asset_error
        return delivery
    if is_development:
        subject = f"[DEV → {address}] {subject}"
    try:
        _smtp_send(actual_recipient, name, subject, body)
        delivery.status = EmailDeliveryStatus.sent
        delivery.sent_at = utcnow()
    except Exception as exc:
        delivery.status = EmailDeliveryStatus.failed
        delivery.error = str(exc)[:2_000]
    return delivery


def _smtp_send(recipient: str, recipient_name: str | None, subject: str, body: str) -> None:
    if not settings.smtp_host:
        raise RuntimeError("SMTP_HOST is not configured.")
    message = EmailMessage()
    message["From"] = formataddr((settings.smtp_from_name, settings.smtp_from_email))
    message["To"] = formataddr((recipient_name or "", recipient))
    message["Subject"] = subject
    message.set_content("This message contains HTML. Please use an HTML-capable email client.")
    message.add_alternative(body, subtype="html")

    smtp_class = smtplib.SMTP_SSL if settings.smtp_ssl else smtplib.SMTP
    with smtp_class(
        settings.smtp_host,
        settings.smtp_port,
        timeout=settings.smtp_timeout_seconds,
    ) as client:
        if settings.smtp_starttls and not settings.smtp_ssl:
            client.starttls()
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password or "")
        client.send_message(message)
