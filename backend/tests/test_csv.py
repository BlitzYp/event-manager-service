import pytest

from app.errors import ApiError
from app.services import validate_participant_csv


def test_valid_csv_is_normalized() -> None:
    rows = validate_participant_csv(
        b"participant_code,name,group,email\nP-1,Ada Lovelace,Speakers,ada@example.com\n"
    )
    assert rows == [
        {
            "participant_code": "P-1",
            "name": "Ada Lovelace",
            "group": "Speakers",
            "email": "ada@example.com",
        }
    ]


@pytest.mark.parametrize(
    "payload",
    [
        b"name\nMissing code\n",
        b"participant_code,name\nP-1,First\nP-1,Duplicate\n",
        b"participant_code,name\n,Missing code\n",
    ],
)
def test_invalid_csv_rejects_the_whole_import(payload: bytes) -> None:
    with pytest.raises(ApiError) as error:
        validate_participant_csv(payload)
    assert error.value.status == 422

