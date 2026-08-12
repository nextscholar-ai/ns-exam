"""
question_bank module router - thin, delegates to service.py (Phase 5 §7).
Real endpoints land in Phase 10 (Question Bank). A placeholder ping route keeps this router
non-empty so it is meaningful to register in app/api/v1/router.py from Phase 1.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/question_bank", tags=["question_bank"])


@router.get("/ping")
async def ping() -> dict[str, str]:
    return {"module": "question_bank", "status": "ok"}
