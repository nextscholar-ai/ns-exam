"""Phase 6 §22: password hashing round-trip."""
from app.core.security.password import hash_password, verify_password


def test_password_hash_round_trip():
    hashed = hash_password("Sup3rSecret1")
    assert hashed != "Sup3rSecret1"
    assert verify_password("Sup3rSecret1", hashed) is True


def test_wrong_password_rejected():
    hashed = hash_password("Sup3rSecret1")
    assert verify_password("wrong-password", hashed) is False
