"""Assert-based checks for the greedy auto-scheduler.

Uses its own in-memory SQLite DB, independent of timetable.db.
Run: python test_scheduler.py
"""
import asyncio

from sqlalchemy import select
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
from scheduler import auto_generate


async def make_session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session = async_sessionmaker(engine, expire_on_commit=False)()
    return session, engine


def make_time_slots():
    return [TimeSlot(slot_number=n, start_time=f"{7+n}:00", end_time=f"{7+n}:50") for n in range(1, 7)]


async def test_no_gaps_and_room_reuse():
    """One group, two 1-hour loads, two equally-fitting rooms.

    Both hours must be placed, land on the same day back-to-back (zero
    windows), and reuse the same room (zero room changes) — both are free
    choices, so the scorer should prefer them over spreading out.
    """
    session, engine = await make_session()
    building = Building(name="B")
    session.add(building)
    await session.flush()
    room_a = Room(building_id=building.id, number="A", capacity=30, is_lab=False, floor=1)
    room_b = Room(building_id=building.id, number="B", capacity=30, is_lab=False, floor=1)
    session.add_all([room_a, room_b])
    teacher_1 = Teacher(full_name="T1", department="D")
    teacher_2 = Teacher(full_name="T2", department="D")
    session.add_all([teacher_1, teacher_2])
    group = StudentGroup(code="G1", students_count=20, course=1)
    session.add(group)
    subject_1 = Subject(name="S1")
    subject_2 = Subject(name="S2")
    session.add_all([subject_1, subject_2])
    session.add_all(make_time_slots())
    await session.flush()

    load_1 = AcademicLoad(subject_id=subject_1.id, teacher_id=teacher_1.id, lesson_type="lecture", total_hours_per_week=1)
    load_2 = AcademicLoad(subject_id=subject_2.id, teacher_id=teacher_2.id, lesson_type="lecture", total_hours_per_week=1)
    session.add_all([load_1, load_2])
    await session.flush()
    session.add_all([
        AcademicLoadGroup(academic_load_id=load_1.id, group_id=group.id),
        AcademicLoadGroup(academic_load_id=load_2.id, group_id=group.id),
    ])
    await session.commit()

    result = await auto_generate(session)
    assert result == {"placed": 2, "unplaced": 0}, result

    items = (await session.execute(select(ScheduleItem))).scalars().all()
    assert len(items) == 2

    slots_by_id = {ts.id: ts.slot_number for ts in (await session.execute(select(TimeSlot))).scalars().all()}
    days = {i.day_of_week for i in items}
    assert len(days) == 1, f"expected both hours on the same day, got days {days}"
    slot_numbers = sorted(slots_by_id[i.time_slot_id] for i in items)
    assert slot_numbers[1] - slot_numbers[0] == 1, f"expected adjacent slots, got {slot_numbers}"
    room_ids = {i.room_id for i in items}
    assert len(room_ids) == 1, f"expected the same room reused, got rooms {room_ids}"

    await session.close()
    await engine.dispose()


async def test_capacity_is_hard_leaves_unplaced():
    """A load too big for every room must stay unplaced, not squeezed in."""
    session, engine = await make_session()
    building = Building(name="B")
    session.add(building)
    await session.flush()
    small_room = Room(building_id=building.id, number="A", capacity=10, is_lab=False, floor=1)
    session.add(small_room)
    teacher = Teacher(full_name="T", department="D")
    session.add(teacher)
    group = StudentGroup(code="G1", students_count=50, course=1)  # too big for the only room
    session.add(group)
    subject = Subject(name="S")
    session.add(subject)
    session.add_all(make_time_slots())
    await session.flush()

    load = AcademicLoad(subject_id=subject.id, teacher_id=teacher.id, lesson_type="lecture", total_hours_per_week=2)
    session.add(load)
    await session.flush()
    session.add(AcademicLoadGroup(academic_load_id=load.id, group_id=group.id))
    await session.commit()

    result = await auto_generate(session)
    assert result == {"placed": 0, "unplaced": 2}, result

    items = (await session.execute(select(ScheduleItem))).scalars().all()
    assert items == []

    await session.close()
    await engine.dispose()


async def test_regenerate_clears_previous_schedule():
    """Running it twice must not accumulate duplicate placements."""
    session, engine = await make_session()
    building = Building(name="B")
    session.add(building)
    await session.flush()
    room = Room(building_id=building.id, number="A", capacity=30, is_lab=False, floor=1)
    session.add(room)
    teacher = Teacher(full_name="T", department="D")
    session.add(teacher)
    group = StudentGroup(code="G1", students_count=10, course=1)
    session.add(group)
    subject = Subject(name="S")
    session.add(subject)
    session.add_all(make_time_slots())
    await session.flush()

    load = AcademicLoad(subject_id=subject.id, teacher_id=teacher.id, lesson_type="lecture", total_hours_per_week=1)
    session.add(load)
    await session.flush()
    session.add(AcademicLoadGroup(academic_load_id=load.id, group_id=group.id))
    await session.commit()

    await auto_generate(session)
    result = await auto_generate(session)
    assert result == {"placed": 1, "unplaced": 0}, result
    items = (await session.execute(select(ScheduleItem))).scalars().all()
    assert len(items) == 1, f"expected exactly 1 item after regenerating twice, got {len(items)}"

    await session.close()
    await engine.dispose()


async def run_checks():
    await test_no_gaps_and_room_reuse()
    await test_capacity_is_hard_leaves_unplaced()
    await test_regenerate_clears_previous_schedule()
    print("OK")


if __name__ == "__main__":
    asyncio.run(run_checks())
