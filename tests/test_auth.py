
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from jwt.exceptions import (
    ExpiredSignatureError,
    InvalidSignatureError,
    MissingRequiredClaimError,
)

from gateway.app.auth import (
    JWT_ALGORITHM,
    JWT_SECRET,
    create_access_token,
    decode_access_token,
    hash_password,
    validate_password_length,
    verify_password,
)


# Password validation tests


def test_password_at_72_bytes_is_valid():
    password = "a" * 72

    validate_password_length(password)


def test_password_over_72_bytes_is_rejected():
    password = "a" * 73

    with pytest.raises(ValueError):
        validate_password_length(password)


def test_unicode_password_over_72_bytes_is_rejected():
    # Each "é" takes 2 bytes in UTF-8.
    password = "é" * 37

    with pytest.raises(ValueError):
        validate_password_length(password)


def test_hash_and_verify_password_successfully():
    password = "FlowMeshSecurePassword123!"

    password_hash = hash_password(password)

    assert verify_password(password, password_hash)


def test_hash_password_rejects_password_over_72_bytes():
    password = "a" * 73

    with pytest.raises(ValueError):
        hash_password(password)


def test_verify_password_rejects_password_over_72_bytes():
    password = "a" * 73
    password_hash = hash_password("valid-password")

    with pytest.raises(ValueError):
        verify_password(password, password_hash)


# JWT tests


def test_create_and_decode_access_token_successfully():
    token = create_access_token("test-user-id")

    payload = decode_access_token(token)

    assert payload["sub"] == "test-user-id"
    assert "iat" in payload
    assert "exp" in payload


def test_decode_access_token_rejects_expired_token():
    now = datetime.now(timezone.utc)

    payload = {
        "sub": "test-user",
        "iat": now - timedelta(days=2),
        "exp": now - timedelta(days=1),
    }

    token = jwt.encode(
        payload,
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )

    with pytest.raises(ExpiredSignatureError):
        decode_access_token(token)


def test_decode_access_token_rejects_invalid_signature():
    now = datetime.now(timezone.utc)

    payload = {
        "sub": "test-user",
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }

    token = jwt.encode(
        payload,
        "this-is-a-different-test-secret-32-bytes",
        algorithm=JWT_ALGORITHM,
    )

    with pytest.raises(InvalidSignatureError):
        decode_access_token(token)


@pytest.mark.parametrize(
    "missing_claim",
    ["sub", "iat", "exp"],
)
def test_decode_access_token_rejects_missing_required_claims(
    missing_claim,
):
    now = datetime.now(timezone.utc)

    payload = {
        "sub": "test-user",
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }

    payload.pop(missing_claim)

    token = jwt.encode(
        payload,
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )

    with pytest.raises(MissingRequiredClaimError):
        decode_access_token(token)
