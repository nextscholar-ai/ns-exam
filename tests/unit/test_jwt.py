"""Phase 6 §22: JWT issue/verify round-trip, expiry handling."""
import time

import pytest

from app.core.exceptions import UnauthorizedError
from app.core.security.jwt import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_refresh_token,
)


def test_access_token_round_trip():
    token, jti = create_access_token(
        public_id="11111111-1111-1111-1111-111111111111",
        user_type="TEACHER",
        auth_source="ERP",
        roles=["TEACHER"],
        school_id=5,
        board_id=1,
    )
    claims = decode_access_token(token)
    assert claims["sub"] == "11111111-1111-1111-1111-111111111111"
    assert claims["user_type"] == "TEACHER"
    assert claims["roles"] == ["TEACHER"]
    assert claims["jti"] == jti


def test_guest_token_has_roughly_four_hour_expiry():
    token, _ = create_access_token(
        public_id="x", user_type="GUEST_STUDENT", auth_source="GUEST", roles=[], is_guest=True
    )
    claims = decode_access_token(token)
    seconds_until_expiry = claims["exp"] - time.time()
    assert 3 * 3600 < seconds_until_expiry <= 4 * 3600


def test_tampered_token_signature_rejected():
    token, _ = create_access_token(
        public_id="x", user_type="TEACHER", auth_source="LOCAL", roles=[]
    )
    tampered = token[:-2] + ("aa" if token[-2:] != "aa" else "bb")
    with pytest.raises(UnauthorizedError):
        decode_access_token(tampered)


def test_refresh_token_hash_is_deterministic_and_not_reversible():
    raw, digest = generate_refresh_token()
    assert hash_refresh_token(raw) == digest
    assert digest != raw
