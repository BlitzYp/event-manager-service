import asyncio
import json

from fastapi import Request
from fastapi.exceptions import RequestValidationError

from app.errors import ApiError, api_error_handler, validation_error_handler
from app.schemas import ActionCreate, ActionWalletScope, LoginRequest, ParticipantUpdate


def request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/", "headers": []})


def test_local_test_admin_email_is_valid() -> None:
    payload = LoginRequest(email=" ADMIN@LOCAL.TEST ", password="password")
    assert payload.email == "admin@local.test"


def test_daily_action_accepts_execution_dates() -> None:
    payload = ActionCreate(
        name="Daily wallet activation",
        action_type="activate_wallets",
        schedule_type="daily",
        execute_at="2026-07-20T07:00:00Z",
        schedule_start="2026-07-20",
        schedule_end="2026-07-25",
        schedule_time="10:00",
    )
    assert payload.schedule_start.isoformat() == "2026-07-20"
    assert payload.schedule_end and payload.schedule_end.isoformat() == "2026-07-25"


def test_daily_action_rejects_reversed_execution_dates() -> None:
    try:
        ActionCreate(
            name="Invalid schedule",
            action_type="activate_wallets",
            schedule_type="daily",
            execute_at="2026-07-25T07:00:00Z",
            schedule_start="2026-07-25",
            schedule_end="2026-07-20",
            schedule_time="10:00",
        )
    except ValueError as exc:
        assert "end date" in str(exc)
    else:
        raise AssertionError("A reversed daily schedule should be rejected.")


def test_participant_update_accepts_editable_code() -> None:
    payload = ParticipantUpdate(
        participant_code="P-002",
        name="Updated participant",
        group="Guests",
    )
    assert payload.participant_code == "P-002"


def test_action_wallet_scope_requires_wallets() -> None:
    payload = ActionWalletScope(operation="execute", wallet_ids=[3, 4])
    assert payload.wallet_ids == [3, 4]
    try:
        ActionWalletScope(operation="execute", wallet_ids=[])
    except ValueError as exc:
        assert "at least 1" in str(exc)
    else:
        raise AssertionError("An empty wallet scope should be rejected.")


def test_api_error_handler_preserves_status_and_structure() -> None:
    response = asyncio.run(
        api_error_handler(request(), ApiError(401, "invalid_credentials", "Invalid login."))
    )
    assert response.status_code == 401
    assert json.loads(response.body)["error"]["code"] == "invalid_credentials"


def test_validation_handler_returns_field_errors() -> None:
    error = RequestValidationError(
        [
            {
                "type": "missing",
                "loc": ("body", "email"),
                "msg": "Field required",
                "input": {},
            }
        ]
    )
    response = asyncio.run(validation_error_handler(request(), error))
    body = json.loads(response.body)
    assert response.status_code == 422
    assert body["error"]["fields"] == [{"path": "email", "message": "Field required"}]
