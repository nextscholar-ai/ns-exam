"""Aggregates every bounded-context module router under a single /api/v1 prefix.

Per Phase 2 §11's one-directional dependency graph, this is the ONE place
allowed to import from every module - it is glue, not business logic.
"""
from fastapi import APIRouter

from app.modules.academic.router import router as academic_router
from app.modules.analytics.router import router as analytics_router
from app.modules.blueprint.router import router as blueprint_router
from app.modules.evaluation.router import router as evaluation_router
from app.modules.exam_management.router import router as exam_management_router
from app.modules.identity.router import router as identity_router
from app.modules.integration.router import router as integration_router
from app.modules.learning_profile.router import router as learning_profile_router
from app.modules.paper_generation.router import router as paper_generation_router
from app.modules.question_bank.router import router as question_bank_router
from app.modules.recommendation.router import router as recommendation_router
from app.modules.reports.router import router as reports_router
from app.modules.storage.router import router as storage_router
from app.modules.student.router import router as student_router
from app.modules.teacher.router import router as teacher_router

api_v1_router = APIRouter()

# Order follows Phase 2 §11's module dependency graph.
api_v1_router.include_router(identity_router)
api_v1_router.include_router(academic_router)
api_v1_router.include_router(student_router)
api_v1_router.include_router(teacher_router)
api_v1_router.include_router(question_bank_router)
api_v1_router.include_router(blueprint_router)
api_v1_router.include_router(paper_generation_router)
api_v1_router.include_router(exam_management_router)
api_v1_router.include_router(evaluation_router)
api_v1_router.include_router(learning_profile_router)
api_v1_router.include_router(analytics_router)
api_v1_router.include_router(recommendation_router)
api_v1_router.include_router(reports_router)
api_v1_router.include_router(storage_router)
api_v1_router.include_router(integration_router)
