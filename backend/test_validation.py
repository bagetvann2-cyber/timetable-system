"""Assert-based checks for find_conflicts (rules a/b/c/d + lab + no-room-id path).

Uses its own in-memory SQLite DB, independent of timetable.db.
Run: python test_validation.py
"""
import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from database.models import (
    AcademicLoad,
    AcademicLoadGroup,
    Base,
    Building,
    Room,
    ScheduleItem,
    StudentGroup,
    Subject,
    Teacher,
    TimeSlot,
)
from main import find_conflicts, get_load_or_404


async def make_session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session = async_sessionmaker(engine, expire_on_commit=False)()
    return session, engine


async def seed_minimal(session):
    """2 rooms, 3 teachers, 3 groups, 3 loads, 1 placed item.

    - small_room: capacity 20, not a lab.
    - lab_room: capacity 30, is a lab.
    - placed_item: teacher_a teaches group_1 (25 students) in small_room,
      slot_1, day 1. (Room is smaller than the group on purpose — it's
      already placed, existing data doesn't have to be clean.)
    - lab_load: teacher_b, type "lab", groups [group_1, group_2] = 35 students.
      Shares group_1 and slot with placed_item -> exercises rules a/b/c/d/lab.
    - clean_load: teacher_c, type "lecture", group [group_3] = 35 students.
      No teacher/group overlap with placed_item -> isolates the
      no-room-id "no fitting room" warning from rule c.
    """
    building = Building(name="Корпус")
    session.add(building)
    await session.flush()

    small_room = Room(building_id=building.id, number="A-1", capacity=20, is_lab=False, floor=1)
    lab_room = Room(building_id=building.id, number="A-2", capacity=30, is_lab=True, floor=1)
    session.add_all([small_room, lab_room])

    teacher_a = Teacher(full_name="Преп. А", department="Каф.")
    teacher_b = Teacher(full_name="Преп. Б", department="Каф.")
    teacher_c = Teacher(full_name="Преп. В", department="Каф.")
    session.add_all([teacher_a, teacher_b, teacher_c])

    group_1 = StudentGroup(code="Г-1", students_count=25, course=1)
    group_2 = StudentGroup(code="Г-2", students_count=10, course=1)
    group_3 = StudentGroup(code="Г-3", students_count=35, course=1)
    session.add_all([group_1, group_2, group_3])

    subject = Subject(name="Предмет")
    session.add(subject)

    slot_1 = TimeSlot(slot_number=1, start_time="08:00", end_time="08:50")
    slot_2 = TimeSlot(slot_number=2, start_time="09:00", end_time="09:50")
    session.add_all([slot_1, slot_2])
    await session.flush()

    placed_load = AcademicLoad(
        subject_id=subject.id, teacher_id=teacher_a.id,
        lesson_type="lecture", total_hours_per_week=2,
    )
    lab_load = AcademicLoad(
        subject_id=subject.id, teacher_id=teacher_b.id,
        lesson_type="lab", total_hours_per_week=2,
    )
    clean_load = AcademicLoad(
        subject_id=subject.id, teacher_id=teacher_c.id,
        lesson_type="lecture", total_hours_per_week=2,
    )
    session.add_all([placed_load, lab_load, clean_load])
    await session.flush()

    session.add_all([
        AcademicLoadGroup(academic_load_id=placed_load.id, group_id=group_1.id),
        AcademicLoadGroup(academic_load_id=lab_load.id, group_id=group_1.id),
        AcademicLoadGroup(academic_load_id=lab_load.id, group_id=group_2.id),
        AcademicLoadGroup(academic_load_id=clean_load.id, group_id=group_3.id),
    ])

    placed_item = ScheduleItem(
        academic_load_id=placed_load.id, room_id=small_room.id,
        time_slot_id=slot_1.id, day_of_week=1,
    )
    session.add(placed_item)
    await session.commit()

    return {
        "small_room": small_room, "lab_room": lab_room,
        "slot_1": slot_1, "slot_2": slot_2,
        "placed_load": placed_load, "placed_item": placed_item,
        "lab_load": lab_load, "clean_load": clean_load,
    }


async def run_checks():
    session, engine = await make_session()
    data = await seed_minimal(session)

    lab_load = await get_load_or_404(session, data["lab_load"].id)
    placed_load = await get_load_or_404(session, data["placed_load"].id)
    clean_load = await get_load_or_404(session, data["clean_load"].id)

    # a) room busy: lab_load into small_room at slot_1/day 1 (already holds placed_item)
    errors, _ = await find_conflicts(
        session, lab_load, 1, data["slot_1"].id, data["small_room"].id, None
    )
    assert any("занята" in e for e in errors), f"expected room-busy error, got {errors}"

    # b) teacher busy: placed_load's own teacher (teacher_a) can't teach elsewhere
    # at the same day/slot as placed_item. A second, group-less load for teacher_a
    # isolates rule b from rules a/c (no room or group overlap involved).
    second_load_for_teacher_a = AcademicLoad(
        subject_id=placed_load.subject_id, teacher_id=placed_load.teacher_id,
        lesson_type="lecture", total_hours_per_week=1,
    )
    session.add(second_load_for_teacher_a)
    await session.commit()
    second_load_for_teacher_a = await get_load_or_404(session, second_load_for_teacher_a.id)
    errors, _ = await find_conflicts(
        session, second_load_for_teacher_a, 1, data["slot_1"].id, data["lab_room"].id, None
    )
    assert any("ведёт пару" in e for e in errors), f"expected teacher-busy error, got {errors}"

    # c) group busy: lab_load shares group_1 with placed_item at slot_1/day 1
    errors, _ = await find_conflicts(
        session, lab_load, 1, data["slot_1"].id, data["lab_room"].id, None
    )
    assert any("уже на паре" in e for e in errors), f"expected group-busy error, got {errors}"

    # d) capacity warning + lab-equipment warning: lab_load (35 students, type lab)
    # into small_room (capacity 20, not a lab) at a conflict-free slot.
    errors, warnings = await find_conflicts(
        session, lab_load, 2, data["slot_2"].id, data["small_room"].id, None
    )
    assert errors == [], f"expected no errors, got {errors}"
    assert any("Вместимость" in w for w in warnings), f"expected capacity warning, got {warnings}"
    assert any("Лабораторная" in w for w in warnings), f"expected lab warning, got {warnings}"

    # Clean placement: lab_load into lab_room (capacity 30) still short by 5 seats,
    # so switch to group_2 alone (10 students) via clean_load's teacher/groups is
    # simpler: just check lab_room at slot_2 has no lab-warning (it IS a lab) even
    # though capacity 30 < 35 still warns.
    errors, warnings = await find_conflicts(
        session, lab_load, 2, data["slot_2"].id, data["lab_room"].id, None
    )
    assert errors == [], f"expected no errors, got {errors}"
    assert not any("Лабораторная" in w for w in warnings), f"lab_room is a lab, got {warnings}"
    assert any("Вместимость" in w for w in warnings), f"30 < 35 should still warn, got {warnings}"

    # current_item_id: moving placed_item to its own slot must not conflict with itself
    errors, _ = await find_conflicts(
        session, placed_load, 1, data["slot_1"].id, data["small_room"].id,
        current_item_id=data["placed_item"].id,
    )
    assert errors == [], f"expected self-move to be conflict-free, got {errors}"

    # No room_id, no group/teacher conflict: small_room is taken (irrelevant here),
    # lab_room (30) is free but too small for clean_load's 35 students -> warning only.
    errors, warnings = await find_conflicts(
        session, clean_load, 1, data["slot_1"].id, None, None
    )
    assert errors == [], f"expected no hard error (a room is free), got {errors}"
    assert any("Нет подходящей" in w for w in warnings), f"expected suitability warning, got {warnings}"

    # No room_id, group conflict: rule c fires even without a room chosen.
    errors, _ = await find_conflicts(
        session, lab_load, 1, data["slot_1"].id, None, None
    )
    assert any("уже на паре" in e for e in errors), f"expected group conflict, got {errors}"

    await session.close()
    await engine.dispose()
    print("OK")


if __name__ == "__main__":
    asyncio.run(run_checks())
