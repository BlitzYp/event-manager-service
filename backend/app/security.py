import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from .config import settings

password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)


# Opaque wallet/session secrets and deterministic keyed lookup values.
def new_token(size: int = 32) -> str:
    """Return a cryptographically random URL-safe secret for one-time delivery to a client."""
    return secrets.token_urlsafe(size)


def token_hash(value: str) -> str:
    """Return a SHA-256 digest used to store and look up an opaque token without its raw value."""
    return hashlib.sha256(value.encode()).hexdigest()


def keyed_lookup(value: str, purpose: str) -> str:
    """Return a purpose-separated HMAC for deterministic PIN lookup or coupon signatures."""
    key = f"{purpose}:{settings.app_secret_key}".encode()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


# Signed coupon QR payloads and human-enterable coupon codes.
def coupon_token(coupon_id: int) -> str:
    """Return a signed QR payload identifying one coupon without exposing the signing key."""
    value = str(coupon_id)
    signature = keyed_lookup(value, "coupon")[:32]
    return f"coupon.{value}.{signature}"


def coupon_id_from_token(value: str) -> int | None:
    """Return a coupon ID only if the QR payload structure and signature are valid."""
    parts = value.split(".")
    if len(parts) != 3 or parts[0] != "coupon" or not parts[1].isdigit():
        return None
    expected = coupon_token(int(parts[1]))
    return int(parts[1]) if hmac.compare_digest(value, expected) else None


def coupon_code(coupon_id: int) -> str:
    """Return a short, human-enterable, tamper-evident coupon code."""
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    value, encoded = coupon_id, ""
    while value:
        value, remainder = divmod(value, 36)
        encoded = alphabet[remainder] + encoded
    encoded = encoded or "0"
    signature = keyed_lookup(str(coupon_id), "coupon-code")[:8].upper()
    return f"CP-{encoded}-{signature}"


def coupon_id_from_code(value: str) -> int | None:
    """Return a coupon ID for a valid human-enterable code, otherwise None."""
    parts = value.strip().upper().split("-")
    if len(parts) != 3 or parts[0] != "CP":
        return None
    try:
        coupon_id = int(parts[1], 36)
    except ValueError:
        return None
    expected = coupon_code(coupon_id)
    return coupon_id if hmac.compare_digest(value.strip().upper(), expected) else None


# Argon2id credentials and constant-time verification.
def hash_password(value: str) -> str:
    """Return an Argon2id hash for a password or vendor PIN; never store the plaintext."""
    return password_hasher.hash(value)


def verify_password(value: str, encoded: str) -> bool:
    """Return whether a password/PIN matches its Argon2 hash; invalid hashes return False."""
    try:
        return password_hasher.verify(encoded, value)
    except (VerifyMismatchError, InvalidHashError):
        return False


def safe_equal_hash(raw: str, expected_hash: str) -> bool:
    """Return whether a raw token matches a stored digest using constant-time comparison."""
    return hmac.compare_digest(token_hash(raw), expected_hash)
