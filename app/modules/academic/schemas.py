"""Academic module — read-only response schemas (Phase 4 §6.2 fields)."""
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel


class BoardOut(BaseModel):
    public_id: UUID
    name: str
    code: str | None
    status: str
    sync_status: str

    model_config = {"from_attributes": True}


class SchoolOut(BaseModel):
    public_id: UUID
    board_id: int
    name: str
    status: str
    sync_status: str

    model_config = {"from_attributes": True}


class AcademicSessionOut(BaseModel):
    public_id: UUID
    school_id: int
    name: str
    start_date: date
    end_date: date
    is_current: bool

    model_config = {"from_attributes": True}


class ClassOut(BaseModel):
    public_id: UUID
    school_id: int
    name: str

    model_config = {"from_attributes": True}


class SubjectOut(BaseModel):
    public_id: UUID
    board_id: int
    class_id: int
    name: str

    model_config = {"from_attributes": True}


class ChapterOut(BaseModel):
    public_id: UUID
    subject_id: int
    name: str
    sequence: int | None

    model_config = {"from_attributes": True}


class UnitOut(BaseModel):
    public_id: UUID
    chapter_id: int
    name: str

    model_config = {"from_attributes": True}


class TopicOut(BaseModel):
    public_id: UUID
    unit_id: int
    name: str

    model_config = {"from_attributes": True}
