"""Drops and recreates all tables, then fills them with sample data.

Run: python seed.py
"""
import asyncio

from database.models import (
    AcademicLoad,
    AcademicLoadGroup,
    Base,
    Building,
    Room,
    StudentGroup,
    Subject,
    Teacher,
    TimeSlot,
    async_session,
    engine,
)


async def seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        main_building = Building(name="Главный корпус")
        session.add(main_building)
        await session.flush()

        rooms = [
            Room(building_id=main_building.id, number="1/101", capacity=60, is_lab=False, floor=1),
            Room(building_id=main_building.id, number="2/201", capacity=40, is_lab=False, floor=2),
            Room(building_id=main_building.id, number="3/509", capacity=25, is_lab=False, floor=5),
            Room(building_id=main_building.id, number="1/110", capacity=20, is_lab=True, floor=1),
            Room(building_id=main_building.id, number="4/305", capacity=15, is_lab=True, floor=3),
        ]
        session.add_all(rooms)

        teachers = [
            Teacher(full_name="Шаяхметов И.", department="Робототехника"),
            Teacher(full_name="Ким А.С.", department="Информационные системы"),
            Teacher(full_name="Нурланова Д.Б.", department="Информационные системы"),
        ]
        session.add_all(teachers)

        groups = [
            StudentGroup(code="ИС-242/1", students_count=25, course=2),
            StudentGroup(code="ИС-242/2", students_count=22, course=2),
            StudentGroup(code="ИС-231", students_count=24, course=3),
            StudentGroup(code="ПМ-221", students_count=19, course=2),
        ]
        session.add_all(groups)

        subjects = [
            Subject(name="Робототехника и IoT"),
            Subject(name="Базы данных"),
            Subject(name="Алгоритмы и структуры данных"),
            Subject(name="Веб-разработка"),
            Subject(name="Операционные системы"),
        ]
        session.add_all(subjects)

        time_slots = [
            TimeSlot(slot_number=1, start_time="08:00", end_time="08:50"),
            TimeSlot(slot_number=2, start_time="09:00", end_time="09:50"),
            TimeSlot(slot_number=3, start_time="10:00", end_time="10:50"),
            TimeSlot(slot_number=4, start_time="11:00", end_time="11:50"),
            TimeSlot(slot_number=5, start_time="12:00", end_time="12:50"),
            TimeSlot(slot_number=6, start_time="13:00", end_time="13:50"),
        ]
        session.add_all(time_slots)

        await session.flush()  # assign ids to rooms/teachers/groups/subjects

        room_101, room_201, room_509, room_110, room_305 = rooms
        shayakhmetov, kim, nurlanova = teachers
        is242_1, is242_2, is231, pm221 = groups
        robotics, databases, algorithms, webdev, os_subj = subjects

        loads = [
            AcademicLoad(
                subject_id=robotics.id,
                teacher_id=shayakhmetov.id,
                lesson_type="lecture",
                total_hours_per_week=2,
            ),  # stream lecture for is242_1 + is242_2 = 47 students
            AcademicLoad(
                subject_id=robotics.id,
                teacher_id=shayakhmetov.id,
                lesson_type="lab",
                total_hours_per_week=2,
            ),
            AcademicLoad(
                subject_id=databases.id,
                teacher_id=kim.id,
                lesson_type="lecture",
                total_hours_per_week=2,
            ),
            AcademicLoad(
                subject_id=databases.id,
                teacher_id=kim.id,
                lesson_type="practice",
                total_hours_per_week=2,
            ),
            AcademicLoad(
                subject_id=algorithms.id,
                teacher_id=nurlanova.id,
                lesson_type="lecture",
                total_hours_per_week=2,
            ),
            AcademicLoad(
                subject_id=algorithms.id,
                teacher_id=nurlanova.id,
                lesson_type="practice",
                total_hours_per_week=2,
            ),
            AcademicLoad(
                subject_id=webdev.id,
                teacher_id=kim.id,
                lesson_type="lab",
                total_hours_per_week=2,
            ),
            AcademicLoad(
                subject_id=os_subj.id,
                teacher_id=nurlanova.id,
                lesson_type="lecture",
                total_hours_per_week=1,
            ),
        ]
        session.add_all(loads)
        await session.flush()

        (
            robotics_lecture,
            robotics_lab,
            db_lecture,
            db_practice,
            algo_lecture,
            algo_practice,
            webdev_lab,
            os_lecture,
        ) = loads

        load_groups = [
            # Robotics lecture: stream of two groups, 25 + 22 = 47 students.
            AcademicLoadGroup(academic_load_id=robotics_lecture.id, group_id=is242_1.id),
            AcademicLoadGroup(academic_load_id=robotics_lecture.id, group_id=is242_2.id),
            AcademicLoadGroup(academic_load_id=robotics_lab.id, group_id=is242_1.id),
            AcademicLoadGroup(academic_load_id=db_lecture.id, group_id=is231.id),
            AcademicLoadGroup(academic_load_id=db_practice.id, group_id=is231.id),
            AcademicLoadGroup(academic_load_id=algo_lecture.id, group_id=pm221.id),
            AcademicLoadGroup(academic_load_id=algo_practice.id, group_id=pm221.id),
            AcademicLoadGroup(academic_load_id=webdev_lab.id, group_id=is242_2.id),
            AcademicLoadGroup(academic_load_id=os_lecture.id, group_id=is231.id),
        ]
        session.add_all(load_groups)

        await session.commit()

    print("Seed complete: 1 building, 5 rooms, 3 teachers, 4 groups, "
          "5 subjects, 6 time slots, 8 academic loads.")


if __name__ == "__main__":
    asyncio.run(seed())
