"""CRUD for the reference entities (buildings, rooms, teachers, groups,
subjects, time slots, academic loads).

Deletes cascade by hand (SQLite here doesn't enforce FK-level cascades):
deleting a building drops its rooms and any schedule items in them, deleting
a teacher drops their load cards and those cards' items/group links, etc.
There are no separate GET endpoints — the frontend reloads everything via
GET /api/initial-data (in main.py) after any mutation, same as assign/unassign.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    AcademicLoad,
    AcademicLoadGroup,
    Building,
    Room,
    ScheduleItem,
    StudentGroup,
    Subject,
    Teacher,
    TimeSlot,
    get_session,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Buildings
# ---------------------------------------------------------------------------


@router.post("/api/buildings")
async def create_building(data: BuildingIn, session: AsyncSession = Depends(get_session)):
    building = Building(**data.model_dump())
    session.add(building)
    await session.commit()
    await session.refresh(building)
    return {"id": building.id, "name": building.name}


@router.put("/api/buildings/{building_id}")
async def update_building(
    building_id: int, data: BuildingIn, session: AsyncSession = Depends(get_session)
):
    building = await session.get(Building, building_id)
    if building is None:
        raise HTTPException(404, "Корпус не найден")
    building.name = data.name
    await session.commit()
    return {"id": building.id, "name": building.name}


@router.delete("/api/buildings/{building_id}", status_code=204)
async def delete_building(building_id: int, session: AsyncSession = Depends(get_session)):
    building = await session.get(Building, building_id)
    if building is None:
        raise HTTPException(404, "Корпус не найден")
    room_ids = (
        await session.execute(select(Room.id).where(Room.building_id == building_id))
    ).scalars().all()
    if room_ids:
        await session.execute(sa_delete(ScheduleItem).where(ScheduleItem.room_id.in_(room_ids)))
        await session.execute(sa_delete(Room).where(Room.building_id == building_id))
    await session.delete(building)
    await session.commit()


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------


async def get_building_or_404(session: AsyncSession, building_id: int) -> None:
    if await session.get(Building, building_id) is None:
        raise HTTPException(404, "Корпус не найден")


@router.post("/api/rooms")
async def create_room(data: RoomIn, session: AsyncSession = Depends(get_session)):
    await get_building_or_404(session, data.building_id)
    room = Room(**data.model_dump())
    session.add(room)
    await session.commit()
    await session.refresh(room)
    return {"id": room.id, **data.model_dump()}


@router.put("/api/rooms/{room_id}")
async def update_room(room_id: int, data: RoomIn, session: AsyncSession = Depends(get_session)):
    room = await session.get(Room, room_id)
    if room is None:
        raise HTTPException(404, "Аудитория не найдена")
    await get_building_or_404(session, data.building_id)
    for field, value in data.model_dump().items():
        setattr(room, field, value)
    await session.commit()
    return {"id": room.id, **data.model_dump()}


@router.delete("/api/rooms/{room_id}", status_code=204)
async def delete_room(room_id: int, session: AsyncSession = Depends(get_session)):
    room = await session.get(Room, room_id)
    if room is None:
        raise HTTPException(404, "Аудитория не найдена")
    await session.execute(sa_delete(ScheduleItem).where(ScheduleItem.room_id == room_id))
    await session.delete(room)
    await session.commit()


# ---------------------------------------------------------------------------
# Teachers
# ---------------------------------------------------------------------------


async def cascade_delete_loads(session: AsyncSession, load_ids: list[int]) -> None:
    """Drop schedule items and group links for a set of academic_loads."""
    if not load_ids:
        return
    await session.execute(sa_delete(ScheduleItem).where(ScheduleItem.academic_load_id.in_(load_ids)))
    await session.execute(
        sa_delete(AcademicLoadGroup).where(AcademicLoadGroup.academic_load_id.in_(load_ids))
    )
    await session.execute(sa_delete(AcademicLoad).where(AcademicLoad.id.in_(load_ids)))


@router.post("/api/teachers")
async def create_teacher(data: TeacherIn, session: AsyncSession = Depends(get_session)):
    teacher = Teacher(**data.model_dump())
    session.add(teacher)
    await session.commit()
    await session.refresh(teacher)
    return {"id": teacher.id, **data.model_dump()}


@router.put("/api/teachers/{teacher_id}")
async def update_teacher(
    teacher_id: int, data: TeacherIn, session: AsyncSession = Depends(get_session)
):
    teacher = await session.get(Teacher, teacher_id)
    if teacher is None:
        raise HTTPException(404, "Преподаватель не найден")
    teacher.full_name = data.full_name
    teacher.department = data.department
    await session.commit()
    return {"id": teacher.id, **data.model_dump()}


@router.delete("/api/teachers/{teacher_id}", status_code=204)
async def delete_teacher(teacher_id: int, session: AsyncSession = Depends(get_session)):
    teacher = await session.get(Teacher, teacher_id)
    if teacher is None:
        raise HTTPException(404, "Преподаватель не найден")
    load_ids = (
        await session.execute(select(AcademicLoad.id).where(AcademicLoad.teacher_id == teacher_id))
    ).scalars().all()
    await cascade_delete_loads(session, load_ids)
    await session.delete(teacher)
    await session.commit()


# ---------------------------------------------------------------------------
# Subjects
# ---------------------------------------------------------------------------


@router.post("/api/subjects")
async def create_subject(data: SubjectIn, session: AsyncSession = Depends(get_session)):
    subject = Subject(**data.model_dump())
    session.add(subject)
    await session.commit()
    await session.refresh(subject)
    return {"id": subject.id, "name": subject.name}


@router.put("/api/subjects/{subject_id}")
async def update_subject(
    subject_id: int, data: SubjectIn, session: AsyncSession = Depends(get_session)
):
    subject = await session.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(404, "Предмет не найден")
    subject.name = data.name
    await session.commit()
    return {"id": subject.id, "name": subject.name}


@router.delete("/api/subjects/{subject_id}", status_code=204)
async def delete_subject(subject_id: int, session: AsyncSession = Depends(get_session)):
    subject = await session.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(404, "Предмет не найден")
    load_ids = (
        await session.execute(select(AcademicLoad.id).where(AcademicLoad.subject_id == subject_id))
    ).scalars().all()
    await cascade_delete_loads(session, load_ids)
    await session.delete(subject)
    await session.commit()


# ---------------------------------------------------------------------------
# Student groups
# ---------------------------------------------------------------------------


@router.post("/api/groups")
async def create_group(data: GroupIn, session: AsyncSession = Depends(get_session)):
    group = StudentGroup(**data.model_dump())
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return {"id": group.id, **data.model_dump()}


@router.put("/api/groups/{group_id}")
async def update_group(group_id: int, data: GroupIn, session: AsyncSession = Depends(get_session)):
    group = await session.get(StudentGroup, group_id)
    if group is None:
        raise HTTPException(404, "Группа не найдена")
    for field, value in data.model_dump().items():
        setattr(group, field, value)
    await session.commit()
    return {"id": group.id, **data.model_dump()}


@router.delete("/api/groups/{group_id}", status_code=204)
async def delete_group(group_id: int, session: AsyncSession = Depends(get_session)):
    group = await session.get(StudentGroup, group_id)
    if group is None:
        raise HTTPException(404, "Группа не найдена")

    affected_load_ids = (
        await session.execute(
            select(AcademicLoadGroup.academic_load_id).where(AcademicLoadGroup.group_id == group_id)
        )
    ).scalars().all()
    await session.execute(sa_delete(AcademicLoadGroup).where(AcademicLoadGroup.group_id == group_id))

    if affected_load_ids:
        # A load left with zero groups is meaningless — drop it too.
        still_has_groups = set(
            (
                await session.execute(
                    select(AcademicLoadGroup.academic_load_id).where(
                        AcademicLoadGroup.academic_load_id.in_(affected_load_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        orphaned_load_ids = [lid for lid in affected_load_ids if lid not in still_has_groups]
        await cascade_delete_loads(session, orphaned_load_ids)

    await session.delete(group)
    await session.commit()


# ---------------------------------------------------------------------------
# Time slots
# ---------------------------------------------------------------------------


@router.post("/api/time-slots")
async def create_time_slot(data: TimeSlotIn, session: AsyncSession = Depends(get_session)):
    slot = TimeSlot(**data.model_dump())
    session.add(slot)
    await session.commit()
    await session.refresh(slot)
    return {"id": slot.id, **data.model_dump()}


@router.put("/api/time-slots/{time_slot_id}")
async def update_time_slot(
    time_slot_id: int, data: TimeSlotIn, session: AsyncSession = Depends(get_session)
):
    slot = await session.get(TimeSlot, time_slot_id)
    if slot is None:
        raise HTTPException(404, "Слот не найден")
    for field, value in data.model_dump().items():
        setattr(slot, field, value)
    await session.commit()
    return {"id": slot.id, **data.model_dump()}


@router.delete("/api/time-slots/{time_slot_id}", status_code=204)
async def delete_time_slot(time_slot_id: int, session: AsyncSession = Depends(get_session)):
    slot = await session.get(TimeSlot, time_slot_id)
    if slot is None:
        raise HTTPException(404, "Слот не найден")
    await session.execute(sa_delete(ScheduleItem).where(ScheduleItem.time_slot_id == time_slot_id))
    await session.delete(slot)
    await session.commit()


# ---------------------------------------------------------------------------
# Academic loads
# ---------------------------------------------------------------------------


async def validate_load_refs(session: AsyncSession, data: LoadIn) -> None:
    if await session.get(Subject, data.subject_id) is None:
        raise HTTPException(404, "Предмет не найден")
    if await session.get(Teacher, data.teacher_id) is None:
        raise HTTPException(404, "Преподаватель не найден")
    if data.group_ids:
        found = (
            await session.execute(select(StudentGroup.id).where(StudentGroup.id.in_(data.group_ids)))
        ).scalars().all()
        if len(found) != len(set(data.group_ids)):
            raise HTTPException(404, "Одна или несколько групп не найдены")


@router.post("/api/loads")
async def create_load(data: LoadIn, session: AsyncSession = Depends(get_session)):
    await validate_load_refs(session, data)
    load = AcademicLoad(
        subject_id=data.subject_id,
        teacher_id=data.teacher_id,
        lesson_type=data.lesson_type,
        total_hours_per_week=data.total_hours_per_week,
    )
    session.add(load)
    await session.flush()
    session.add_all(
        AcademicLoadGroup(academic_load_id=load.id, group_id=gid) for gid in data.group_ids
    )
    await session.commit()
    return {"id": load.id}


@router.put("/api/loads/{load_id}")
async def update_load(load_id: int, data: LoadIn, session: AsyncSession = Depends(get_session)):
    load = await session.get(AcademicLoad, load_id)
    if load is None:
        raise HTTPException(404, "Карточка нагрузки не найдена")
    await validate_load_refs(session, data)

    placed_hours = await session.scalar(
        select(func.count()).select_from(ScheduleItem).where(ScheduleItem.academic_load_id == load_id)
    )
    if data.total_hours_per_week < placed_hours:
        raise HTTPException(
            409, f"Уже расставлено {placed_hours} ч. — нельзя уменьшить ниже этого"
        )

    load.subject_id = data.subject_id
    load.teacher_id = data.teacher_id
    load.lesson_type = data.lesson_type
    load.total_hours_per_week = data.total_hours_per_week

    await session.execute(sa_delete(AcademicLoadGroup).where(AcademicLoadGroup.academic_load_id == load_id))
    session.add_all(
        AcademicLoadGroup(academic_load_id=load_id, group_id=gid) for gid in data.group_ids
    )

    await session.commit()
    return {"id": load.id}


@router.delete("/api/loads/{load_id}", status_code=204)
async def delete_load(load_id: int, session: AsyncSession = Depends(get_session)):
    load = await session.get(AcademicLoad, load_id)
    if load is None:
        raise HTTPException(404, "Карточка нагрузки не найдена")
    await cascade_delete_loads(session, [load_id])
