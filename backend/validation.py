"""The scheduling rule engine: the 4 discrete rules from the spec, plus the
lookup helpers that fetch and 404 the entities they need.

See docs/superpowers/specs/2026-09-14-timetable-system-design.md for the
business rules this implements. Used by schedule_routes.py (manual
assign/validate) — the auto-scheduler (scheduler.py) re-implements these
same rules itself, in-memory, for performance rather than calling this.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import AcademicLoad, Room, ScheduleItem, TimeSlot

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
