"""
recommendation module router - thin, delegates to service.py (Phase 5 §7).
Real endpoints land in Phase 14 (Learning/Mastery/Analytics/Recommendation). A placeholder ping route keeps this router
non-empty so it is meaningful to register in app/api/v1/router.py from Phase 1.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/recommendation", tags=["recommendation"])


@router.get("/ping")
async def ping() -> dict[str, str]:
    return {"module": "recommendation", "status": "ok"}
