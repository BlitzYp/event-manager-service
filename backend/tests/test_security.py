from app.security import (
    coupon_code,
    coupon_id_from_code,
    coupon_id_from_token,
    coupon_token,
    hash_password,
    new_token,
    token_hash,
    verify_password,
)


def test_password_hash_is_salted_and_verifiable() -> None:
    first = hash_password("correct horse battery staple")
    second = hash_password("correct horse battery staple")
    assert first != second
    assert verify_password("correct horse battery staple", first)
    assert not verify_password("incorrect", first)


def test_tokens_are_random_and_only_stable_when_hashed() -> None:
    first, second = new_token(), new_token()
    assert first != second
    assert len(token_hash(first)) == 64
    assert token_hash(first) == token_hash(first)


def test_coupon_token_is_opaque_and_tamper_evident() -> None:
    token = coupon_token(42)
    assert coupon_id_from_token(token) == 42
    assert coupon_id_from_token(token + "x") is None
    assert coupon_id_from_token("coupon.43." + token.rsplit(".", 1)[1]) is None


def test_coupon_code_is_human_enterable_and_tamper_evident() -> None:
    code = coupon_code(42)
    assert code.startswith("CP-")
    assert coupon_id_from_code(code.lower()) == 42
    assert coupon_id_from_code(code[:-1] + ("0" if code[-1] != "0" else "1")) is None
