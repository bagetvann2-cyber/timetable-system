"""Greedy auto-scheduler.

Wipes schedule_items and rebuilds the whole timetable from scratch, one
teaching hour at a time. For every hour it picks the (day, slot, room) that:

1. Never violates a hard rule — room/teacher/group already busy, room too
   small, or (for labs) not a lab room. Capacity and lab-fit are hard here,
   unlike manual assign/validate where they're only warnings: auto-generate
   should not deliberately produce a schedule with warnings.
2. Among the remaining options, minimises (in this order):
   - "windows" in the group's day: for each of the load's groups, the gap
     between the earliest and latest slot they'd be busy that day, minus
     how many of those slots are actually filled.
   - room changes: 0 if adjacent to a same-group hour in the same room,
     1 if same building, 2 if a different building, 0 contribution if
     there's no adjacent hour at all.

Loads are processed biggest-stream-first (by student count, then hours per
week) so the hardest-to-place loads claim rooms while most slots are open.

See docs/superpowers/specs/2026-09-14-timetable-system-design.md for the
manual-assign rules this deliberately differs from (see module docstring
above), and the 2026-09-14 CRUD/auto-generate follow-up discussion for why.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import AcademicLoad, Room, ScheduleItem, TimeSlot

DAYS = range(1, 7)


@dataclass
class Placement:
    academic_load_id: int
    room_id: int
    time_slot_id: int
    day_of_week: int


async def auto_generate(session: AsyncSession) -> dict:
    rooms = (await session.execute(select(Room))).scalars().all()
    time_slots = (
        (await session.execute(select(TimeSlot).order_by(TimeSlot.slot_number)))
        .scalars()
        .all()
    )
    loads = (
        (await session.execute(select(AcademicLoad).options(selectinload(AcademicLoad.groups))))
        .scalars()
        .all()
    )
    room_by_id = {r.id: r for r in rooms}

    # In-memory occupancy — no DB round-trips while scoring candidates.
    room_busy: set[tuple[int, int, int]] = set()  # (room_id, day, time_slot_id)
    teacher_busy: set[tuple[int, int, int]] = set()  # (teacher_id, day, time_slot_id)
    group_busy: set[tuple[int, int, int]] = set()  # (group_id, day, time_slot_id)
    group_day_slots: dict[tuple[int, int], set[int]] = {}  # (group_id, day) -> {slot_number}
    group_slot_room: dict[tuple[int, int, int], int] = {}  # (group_id, day, slot_number) -> room_id

    def room_fits(load: AcademicLoad, room: Room) -> bool:
        students_total = sum(g.students_count for g in load.groups)
        if room.capacity < students_total:
            return False
        if load.lesson_type == "lab" and not room.is_lab:
            return False
        return True

    def room_change_penalty(group_id: int, day: int, neighbor_slot_number: int, candidate_room: Room) -> int:
        """0 if the neighbor hour is in the same room, 1 same building, 2 different. 0 if no neighbor."""
        used_room_id = group_slot_room.get((group_id, day, neighbor_slot_number))
        if used_room_id is None:
            return 0
        if used_room_id == candidate_room.id:
            return 0
        return 1 if room_by_id[used_room_id].building_id == candidate_room.building_id else 2

    def score_candidate(load: AcademicLoad, day: int, slot: TimeSlot, room: Room) -> tuple[int, int]:
        total_gaps = 0
        total_penalty = 0
        for group in load.groups:
            occupied = group_day_slots.get((group.id, day), set())
            candidate = occupied | {slot.slot_number}
            total_gaps += (max(candidate) - min(candidate) + 1) - len(candidate)
            total_penalty += room_change_penalty(group.id, day, slot.slot_number - 1, room)
            total_penalty += room_change_penalty(group.id, day, slot.slot_number + 1, room)
        return (total_gaps, total_penalty)

    # Biggest streams first: fewest fitting rooms, so they should claim
    # slots while the most options are still open.
    ordered_loads = sorted(
        loads,
        key=lambda l: (sum(g.students_count for g in l.groups), l.total_hours_per_week),
        reverse=True,
    )

    placements: list[Placement] = []
    unplaced_hours = 0

    for load in ordered_loads:
        fitting_rooms = [r for r in rooms if room_fits(load, r)]
        for _ in range(load.total_hours_per_week):
            best: tuple[int, TimeSlot, Room] | None = None
            best_score: tuple[int, int] | None = None
            for day in DAYS:
                for slot in time_slots:
                    if (load.teacher_id, day, slot.id) in teacher_busy:
                        continue
                    if any((g.id, day, slot.id) in group_busy for g in load.groups):
                        continue
                    for room in fitting_rooms:
                        if (room.id, day, slot.id) in room_busy:
                            continue
                        score = score_candidate(load, day, slot, room)
                        if best_score is None or score < best_score:
                            best_score = score
                            best = (day, slot, room)
            if best is None:
                unplaced_hours += 1
                continue
            day, slot, room = best
            placements.append(Placement(load.id, room.id, slot.id, day))
            room_busy.add((room.id, day, slot.id))
            teacher_busy.add((load.teacher_id, day, slot.id))
            for group in load.groups:
                group_busy.add((group.id, day, slot.id))
                group_day_slots.setdefault((group.id, day), set()).add(slot.slot_number)
                group_slot_room[(group.id, day, slot.slot_number)] = room.id

    await session.execute(sa_delete(ScheduleItem))
    session.add_all(
        ScheduleItem(
            academic_load_id=p.academic_load_id,
            room_id=p.room_id,
            time_slot_id=p.time_slot_id,
            day_of_week=p.day_of_week,
        )
        for p in placements
    )
    await session.commit()

    return {"placed": len(placements), "unplaced": unplaced_hours}
