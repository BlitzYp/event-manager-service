import pytest

from app.email_service import basic_email_html, render_template, validate_template_document
from app.errors import ApiError
from app.schemas import ActionCreate, EmailSendRequest


def document() -> dict:
    return {
        "root": {
            "type": "EmailLayout",
            "data": {"childrenIds": ["heading"]},
        },
        "heading": {
            "type": "Heading",
            "data": {"props": {"text": "Hello {{participant_first_name}}"}},
        },
    }


def test_email_recipient_scope_is_explicit() -> None:
    selected = EmailSendRequest(template_id=1, participant_ids=[2, 3])
    assert selected.participant_ids == [2, 3]
    with pytest.raises(ValueError):
        EmailSendRequest(
            template_id=1,
            participant_ids=[2],
            recipient_email="person@example.com",
        )


def test_basic_email_requires_subject_and_body() -> None:
    request = EmailSendRequest(
        source="basic",
        subject="Wallet details",
        body="Hello {{participant_first_name}}\n{{public_wallet}}",
        participant_ids=[2],
    )
    assert request.template_id is None
    with pytest.raises(ValueError):
        EmailSendRequest(source="basic", subject="Missing body", participant_ids=[2])


def test_basic_email_sanitizes_formatting_and_links_public_wallet() -> None:
    rendered = basic_email_html(
        '<strong>Hello</strong><script>alert(1)</script>'
        '<span style="position:fixed;color:#238400">Green</span>{{public_wallet}}'
    )
    assert "<strong>Hello</strong>" in rendered
    assert "script" not in rendered
    assert "alert" not in rendered
    assert "position" not in rendered
    assert '<span style="color:#238400">Green</span>' in rendered
    assert '<a href="{{public_wallet}}">Open public wallet</a>' in rendered
    personalized = render_template(
        rendered,
        {"{{public_wallet}}": "https://example.com/wallet?participant=1&event=2"},
        escape_values=True,
    )
    assert (
        'href="https://example.com/wallet?participant=1&amp;event=2"' in personalized
    )


def test_email_action_requires_template() -> None:
    with pytest.raises(ValueError):
        ActionCreate(
            name="Email participants",
            action_type="send_email",
            execute_at="2026-07-24T09:00:00Z",
        )


def test_template_document_rejects_broken_block_links() -> None:
    invalid = document()
    invalid["root"]["data"]["childrenIds"].append("missing")
    with pytest.raises(ApiError) as error:
        validate_template_document(None, 1, invalid, "<h2>Hello</h2>")  # type: ignore[arg-type]
    assert error.value.code == "invalid_template"


def test_template_document_and_personalization_escape_values() -> None:
    encoded = validate_template_document(
        None, 1, document(), "<h2>Hello {{participant_first_name}}</h2>"  # type: ignore[arg-type]
    )
    assert '"EmailLayout"' in encoded
    rendered = render_template(
        "<p>{{participant_name}}</p>",
        {"{{participant_name}}": "<Admin & Guest>"},
        escape_values=True,
    )
    assert rendered == "<p>&lt;Admin &amp; Guest&gt;</p>"
    assert (
        render_template(
            '<a href="%7B%7Bwallet_link%7D%7D">Wallet</a>',
            {"{{wallet_link}}": "https://example.com/wallet"},
            escape_values=True,
        )
        == '<a href="https://example.com/wallet">Wallet</a>'
    )
