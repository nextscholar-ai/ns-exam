"""Phase 6 §22: permission-dependency logic with mocked CurrentUser / tokens."""
import asyncio

import pytest

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security.jwt import create_access_token
from app.core.security.rbac import get_current_user, require_role


def _run(coro):
    return asyncio.run(coro)


def test_get_current_user_requires_bearer_header():
    with pytest.raises(UnauthorizedError):
        _run(get_current_user(authorization=None))
    with pytest.raises(UnauthorizedError):
        _run(get_current_user(authorization="NotBearer abc"))


def test_get_current_user_decodes_valid_token():
    token, _ = create_access_token(
        public_id="abc-123", user_type="TEACHER", auth_source="ERP", roles=["TEACHER"], school_id=5
    )
    user = _run(get_current_user(authorization=f"Bearer {token}"))
    assert user.public_id == "abc-123"
    assert user.user_type == "TEACHER"
    assert user.school_id == 5


def test_require_role_rejects_wrong_role():
    token, _ = create_access_token(
        public_id="abc", user_type="TEACHER", auth_source="ERP", roles=["TEACHER"]
    )

    async def scenario():
        user = await get_current_user(authorization=f"Bearer {token}")
        check = require_role("SUPER_ADMIN", "ADMIN")
        await check(user=user)

    with pytest.raises(ForbiddenError):
        _run(scenario())


def test_require_role_allows_matching_role():
    token, _ = create_access_token(
        public_id="abc", user_type="TEACHER", auth_source="ERP", roles=["TEACHER"]
    )

    async def scenario():
        user = await get_current_user(authorization=f"Bearer {token}")
        check = require_role("TEACHER")
        return await check(user=user)

    result = _run(scenario())
    assert result.user_type == "TEACHER"
