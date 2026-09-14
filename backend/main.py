"""FastAPI app: schemas, conflict validation, and the 4 schedule endpoints.

See docs/superpowers/specs/2026-09-14-timetable-system-design.md for the
business rules this implements.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import (
    AcademicLoad,
    Building,
    Room,
    ScheduleItem,
    StudentGroup,
    Subject,
    Teacher,
    TimeSlot,
    get_session,
    init_db,
)
from references import router as references_router
from scheduler import auto_generate


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Smart Manual Timetable System", lifespan=lifespan)

# Frontend runs on Vite's dev server (5173) during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(references_router)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Shared lookups
# ---------------------------------------------------------------------------


async def get_load_or_404(session: AsyncSession, load_id: int) -> AcademicLoad:
    stmt = (
        select(AcademicLoad)
        .where(AcademicLoad.id == load_id)
        .options(
            selectinload(AcademicLoad.groups),
            selectinload(AcademicLoad.teacher),
            selectinload(AcademicLoad.subject),
        )
    )
    load = (await session.execute(stmt)).scalar_one_or_none()
    if load is None:
        raise HTTPException(404, "Карточка нагрузки не найдена")
    return load


async def get_time_slot_or_404(session: AsyncSession, time_slot_id: int) -> TimeSlot:
    slot = await session.get(TimeSlot, time_slot_id)
    if slot is None:
        raise HTTPException(404, "Временной слот не найден")
    return slot


async def get_room_or_404(session: AsyncSession, room_id: int) -> Room:
    room = await session.get(Room, room_id)
    if room is None:
        raise HTTPException(404, "Аудитория не найдена")
    return room


# ---------------------------------------------------------------------------
# Validation core
# ---------------------------------------------------------------------------


async def find_conflicts(
    session: AsyncSession,
    load: AcademicLoad,
    day_of_week: int,
    time_slot_id: int,
    room_id: int | None,
    current_item_id: int | None,
) -> tuple[list[str], list[str]]:
    """Check the 4 rules from the spec. Returns (errors, warnings).

    errors:   a) room busy, b) teacher busy, c) group busy — placement is impossible.
    warnings: d) room too small, + lab-without-equipment — placement is allowed
              but flagged.
    """
    errors: list[str] = []
    warnings: list[str] = []
    students_total = sum(g.students_count for g in load.groups)

    stmt = (
        select(ScheduleItem)
        .where(
            ScheduleItem.day_of_week == day_of_week,
            ScheduleItem.time_slot_id == time_slot_id,
        )
        .options(
            selectinload(ScheduleItem.academic_load).selectinload(AcademicLoad.groups),
            selectinload(ScheduleItem.academic_load).selectinload(AcademicLoad.teacher),
            selectinload(ScheduleItem.academic_load).selectinload(AcademicLoad.subject),
            selectinload(ScheduleItem.room),
        )
    )
    if current_item_id is not None:
        stmt = stmt.where(ScheduleItem.id != current_item_id)
    items_in_slot = (await session.execute(stmt)).scalars().all()

    # b) teacher busy
    for item in items_in_slot:
        if item.academic_load.teacher_id == load.teacher_id:
            errors.append(
                f"{load.teacher.full_name} уже ведёт пару в аудитории {item.room.number}"
            )
            break

    # c) any of this load's groups already in another lesson
    for item in items_in_slot:
        other_group_ids = {g.id for g in item.academic_load.groups}
        for group in load.groups:
            if group.id in other_group_ids:
                errors.append(
                    f"{group.code} уже на паре: {item.academic_load.subject.name}"
                )

    if room_id is not None:
        room = await get_room_or_404(session, room_id)

        # a) room busy
        for item in items_in_slot:
            if item.room_id == room_id:
                other_groups = ", ".join(g.code for g in item.academic_load.groups)
                errors.append(
                    f"Аудитория {room.number} занята: "
                    f"{item.academic_load.subject.name} ({other_groups})"
                )

        # d) capacity warning
        if room.capacity < students_total:
            warnings.append(
                f"Вместимость {room.capacity} < {students_total} студентов — "
                f"не хватит {students_total - room.capacity} мест"
            )

        # lab-equipment warning
        if load.lesson_type == "lab" and not room.is_lab:
            warnings.append("Лабораторная в аудитории без оборудования")
    else:
        # No room chosen yet (cell-hover highlight): is there any free & suitable room?
        occupied_room_ids = {item.room_id for item in items_in_slot}
        all_rooms = (await session.execute(select(Room))).scalars().all()
        free_rooms = [r for r in all_rooms if r.id not in occupied_room_ids]

        if not free_rooms:
            errors.append("Нет свободных аудиторий в этот слот")
        else:
            suitable = [
                r
                for r in free_rooms
                if r.capacity >= students_total
                and (load.lesson_type != "lab" or r.is_lab)
            ]
            if not suitable:
                if load.lesson_type == "lab" and not any(r.is_lab for r in free_rooms):
                    warnings.append("Нет свободной лаборатории")
                else:
                    best = max(free_rooms, key=lambda r: r.capacity)
                    warnings.append(
                        f"Нет подходящей аудитории на {students_total} мест, "
                        f"самая большая свободная — {best.number} ({best.capacity})"
                    )

    return errors, warnings


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/initial-data")
async def get_initial_data(session: AsyncSession = Depends(get_session)):
    buildings = (await session.execute(select(Building))).scalars().all()
    rooms = (
        (await session.execute(select(Room).options(selectinload(Room.building))))
        .scalars()
        .all()
    )
    teachers = (await session.execute(select(Teacher))).scalars().all()
    groups = (await session.execute(select(StudentGroup))).scalars().all()
    subjects = (await session.execute(select(Subject))).scalars().all()
    time_slots = (
        (await session.execute(select(TimeSlot).order_by(TimeSlot.slot_number)))
        .scalars()
        .all()
    )
    loads = (
        (
            await session.execute(
                select(AcademicLoad).options(selectinload(AcademicLoad.groups))
            )
        )
        .scalars()
        .all()
    )
    items = (await session.execute(select(ScheduleItem))).scalars().all()

    return {
        "buildings": [{"id": b.id, "name": b.name} for b in buildings],
        "rooms": [
            {
                "id": r.id,
                "building_id": r.building_id,
                "building_name": r.building.name,
                "number": r.number,
                "capacity": r.capacity,
                "is_lab": r.is_lab,
                "floor": r.floor,
            }
            for r in rooms
        ],
        "teachers": [
            {"id": t.id, "full_name": t.full_name, "department": t.department}
            for t in teachers
        ],
        "groups": [
            {
                "id": g.id,
                "code": g.code,
                "students_count": g.students_count,
                "course": g.course,
            }
            for g in groups
        ],
        "subjects": [{"id": s.id, "name": s.name} for s in subjects],
        "time_slots": [
            {
                "id": ts.id,
                "slot_number": ts.slot_number,
                "start_time": ts.start_time,
                "end_time": ts.end_time,
            }
            for ts in time_slots
        ],
        "loads": [
            {
                "id": load.id,
                "subject_id": load.subject_id,
                "teacher_id": load.teacher_id,
                "lesson_type": load.lesson_type,
                "total_hours_per_week": load.total_hours_per_week,
                "group_ids": [g.id for g in load.groups],
                "students_total": sum(g.students_count for g in load.groups),
            }
            for load in loads
        ],
        "items": [
            {
                "id": item.id,
                "academic_load_id": item.academic_load_id,
                "room_id": item.room_id,
                "time_slot_id": item.time_slot_id,
                "day_of_week": item.day_of_week,
            }
            for item in items
        ],
    }


@app.post("/api/schedule/validate", response_model=ValidateResponse)
async def validate_schedule(
    req: ValidateRequest, session: AsyncSession = Depends(get_session)
):
    load = await get_load_or_404(session, req.academic_load_id)
    await get_time_slot_or_404(session, req.time_slot_id)
    if req.room_id is not None:
        await get_room_or_404(session, req.room_id)
    if req.current_item_id is not None and (
        await session.get(ScheduleItem, req.current_item_id)
    ) is None:
        raise HTTPException(404, "Пара не найдена")

    errors, warnings = await find_conflicts(
        session,
        load,
        req.day_of_week,
        req.time_slot_id,
        req.room_id,
        req.current_item_id,
    )
    return ValidateResponse(is_valid=len(errors) == 0, errors=errors, warnings=warnings)


@app.post("/api/schedule/assign")
async def assign_schedule(
    req: AssignRequest, session: AsyncSession = Depends(get_session)
):
    load = await get_load_or_404(session, req.academic_load_id)
    await get_time_slot_or_404(session, req.time_slot_id)
    await get_room_or_404(session, req.room_id)

    current_item: ScheduleItem | None = None
    if req.current_item_id is not None:
        current_item = await session.get(ScheduleItem, req.current_item_id)
        if current_item is None:
            raise HTTPException(404, "Пара не найдена")
        if current_item.academic_load_id != req.academic_load_id:
            raise HTTPException(400, "Пара принадлежит другой карточке нагрузки")

    errors, warnings = await find_conflicts(
        session,
        load,
        req.day_of_week,
        req.time_slot_id,
        req.room_id,
        req.current_item_id,
    )
    if errors:
        raise HTTPException(
            409, detail={"is_valid": False, "errors": errors, "warnings": warnings}
        )

    if current_item is None:
        used_hours = await session.scalar(
            select(func.count())
            .select_from(ScheduleItem)
            .where(ScheduleItem.academic_load_id == load.id)
        )
        if used_hours >= load.total_hours_per_week:
            raise HTTPException(
                409,
                detail={
                    "is_valid": False,
                    "errors": ["Все часы уже расставлены"],
                    "warnings": [],
                },
            )
        item = ScheduleItem(
            academic_load_id=load.id,
            room_id=req.room_id,
            time_slot_id=req.time_slot_id,
            day_of_week=req.day_of_week,
        )
        session.add(item)
    else:
        current_item.room_id = req.room_id
        current_item.time_slot_id = req.time_slot_id
        current_item.day_of_week = req.day_of_week
        item = current_item

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            409,
            detail={"is_valid": False, "errors": ["Аудитория занята"], "warnings": []},
        )

    await session.refresh(item)
    return {
        "id": item.id,
        "academic_load_id": item.academic_load_id,
        "room_id": item.room_id,
        "time_slot_id": item.time_slot_id,
        "day_of_week": item.day_of_week,
        "warnings": warnings,
    }


@app.delete("/api/schedule/unassign/{item_id}", status_code=204)
async def unassign_schedule(
    item_id: int, session: AsyncSession = Depends(get_session)
):
    item = await session.get(ScheduleItem, item_id)
    if item is None:
        raise HTTPException(404, "Пара не найдена")
    await session.delete(item)
    await session.commit()


@app.post("/api/schedule/auto-generate")
async def auto_generate_schedule(session: AsyncSession = Depends(get_session)):
    """Wipe the schedule and rebuild it greedily. See scheduler.py."""
    return await auto_generate(session)
