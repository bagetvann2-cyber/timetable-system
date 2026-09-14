"""Pydantic request/response models for the whole API — the schedule
endpoints (validate/assign) and the reference-entity CRUD endpoints share
this one file so every wire contract lives in one place.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# --- schedule (main.py's validate/assign/unassign) --------------------------


class ValidateRequest(BaseModel):
    academic_load_id: int
    day_of_week: int = Field(ge=1, le=6)
    time_slot_id: int
    room_id: int | None = None
    current_item_id: int | None = None


class AssignRequest(BaseModel):
    academic_load_id: int
    day_of_week: int = Field(ge=1, le=6)
    time_slot_id: int
    room_id: int
    current_item_id: int | None = None


class ValidateResponse(BaseModel):
    is_valid: bool
    errors: list[str]
    warnings: list[str]


# --- reference entities (references.py) -------------------------------------


class BuildingIn(BaseModel):
    name: str


class RoomIn(BaseModel):
    building_id: int
    number: str
    capacity: int
    is_lab: bool = False
    floor: int


class TeacherIn(BaseModel):
    full_name: str
    department: str


class GroupIn(BaseModel):
    code: str
    students_count: int
    course: int


class SubjectIn(BaseModel):
    name: str


class TimeSlotIn(BaseModel):
    slot_number: int
    start_time: str
    end_time: str


class LoadIn(BaseModel):
    subject_id: int
    teacher_id: int
    lesson_type: Literal["lecture", "practice", "lab"]
    total_hours_per_week: int
    group_ids: list[int] = []
