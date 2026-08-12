"""
evaluation module router - thin, delegates to service.py (Phase 5 §7).
Real endpoints land in Phase 13 (Evaluation Engine). A placeholder ping route keeps this router
non-empty so it is meaningful to register in app/api/v1/router.py from Phase 1.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.get("/ping")
async def ping() -> dict[str, str]:
    return {"module": "evaluation", "status": "ok"}
