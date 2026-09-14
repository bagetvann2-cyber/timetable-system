"""The 5 schedule endpoints: read the board, validate/assign/unassign one
lesson, and trigger the auto-scheduler. Business rules live in validation.py
(manual assign/validate) and scheduler.py (auto-generate) — this file is
just the HTTP layer over them.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
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
)
from schemas import AssignRequest, ValidateRequest, ValidateResponse
from scheduler import auto_generate
from validation import find_conflicts, get_load_or_404, get_room_or_404, get_time_slot_or_404

router = APIRouter()


@router.get("/api/initial-data")
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


@router.post("/api/schedule/validate", response_model=ValidateResponse)
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


@router.post("/api/schedule/assign")
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


@router.delete("/api/schedule/unassign/{item_id}", status_code=204)
async def unassign_schedule(
    item_id: int, session: AsyncSession = Depends(get_session)
):
    item = await session.get(ScheduleItem, item_id)
    if item is None:
        raise HTTPException(404, "Пара не найдена")
    await session.delete(item)
    await session.commit()


@router.post("/api/schedule/auto-generate")
async def auto_generate_schedule(session: AsyncSession = Depends(get_session)):
    """Wipe the schedule and rebuild it greedily. See scheduler.py."""
    return await auto_generate(session)
