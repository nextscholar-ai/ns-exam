"""
identity module router - thin, delegates to service.py (Phase 5 §7).
Real endpoints land in Phase 6 (Authentication & RBAC). A placeholder ping route keeps this router
non-empty so it is meaningful to register in app/api/v1/router.py from Phase 1.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/identity", tags=["identity"])


@router.get("/ping")
async def ping() -> dict[str, str]:
    return {"module": "identity", "status": "ok"}
