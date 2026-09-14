"""Drops and recreates all tables, then fills them with generated sample data:
3 buildings x 5 floors x 15 rooms = 225 rooms, ~25 teachers, ~20 subjects,
50 student groups, and academic loads mixing multi-group stream lectures
with per-group practicals/labs.

Uses a fixed random seed so re-running this gives the same dataset every
time (useful for demoing and for comparing auto-generate runs).

Run: python seed.py
"""
import asyncio
import random

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

RANDOM_SEED = 20260914

BUILDING_NAMES = ["Главный корпус", "Корпус 2", "Корпус 3"]
FLOORS_PER_BUILDING = 5
ROOMS_PER_FLOOR = 15

DEPARTMENTS = [
    "Информационные системы",
    "Робототехника",
    "Математика",
    "Физика",
    "Экономика",
    "Гуманитарные науки",
    "Информационная безопасность",
]

TEACHER_NAMES = [
    "Шаяхметов И.", "Ким А.С.", "Нурланова Д.Б.", "Ахметов Б.К.", "Сергеева О.П.",
    "Ли Ч.В.", "Токтаров Е.М.", "Байжанова А.С.", "Волков Д.И.", "Смагулова Г.Т.",
    "Петров И.А.", "Джаксыбеков Н.К.", "Романова Е.В.", "Утеулиев А.Ж.", "Ким В.С.",
    "Абдуллаева М.Р.", "Соколов П.Н.", "Тлеубердина А.К.", "Морозов С.Л.", "Есенова Г.Б.",
    "Кузнецов А.В.", "Оспанова Д.М.", "Игнатьев Р.О.", "Бекова С.А.", "Жумабеков Т.А.",
]

SUBJECT_NAMES = [
    "Робототехника и IoT", "Базы данных", "Алгоритмы и структуры данных",
    "Веб-разработка", "Операционные системы", "Компьютерные сети",
    "Математический анализ", "Линейная алгебра", "Физика", "Теория вероятностей",
    "Объектно-ориентированное программирование", "Дискретная математика",
    "Экономика", "Иностранный язык", "Философия", "Информационная безопасность",
    "Машинное обучение", "Архитектура компьютеров", "Компиляторы", "Инженерная графика",
]

SPECIALTIES = ["ИС", "ПМ", "ВТ", "ЭК", "ЮР"]
COURSES = [1, 2, 3, 4]
GROUP_COUNT = 50


def generate_rooms(building: Building) -> list[Room]:
    rooms = []
    for floor in range(1, FLOORS_PER_BUILDING + 1):
        for seq in range(1, ROOMS_PER_FLOOR + 1):
            is_lecture_hall = random.random() < 0.12
            is_lab = (not is_lecture_hall) and random.random() < 0.2
            capacity = random.randint(55, 90) if is_lecture_hall else random.randint(20, 40)
            rooms.append(
                Room(
                    building_id=building.id,
                    number=f"{floor}/{floor}{seq:02d}",
                    capacity=capacity,
                    is_lab=is_lab,
                    floor=floor,
                )
            )
    return rooms


def generate_groups() -> list[dict]:
    """50 groups spread across 5 specialties x 4 courses, 2-3 sections each."""
    combos = [(spec, course) for spec in SPECIALTIES for course in COURSES]  # 20 combos
    sections_by_combo = {combo: 2 for combo in combos}  # 40 groups
    extra_combos = combos[:GROUP_COUNT - 40]  # 10 more -> 50
    for combo in extra_combos:
        sections_by_combo[combo] += 1

    groups = []
    for (spec, course), section_count in sections_by_combo.items():
        for section in range(1, section_count + 1):
            groups.append(
                {
                    "specialty": spec,
                    "course": course,
                    "code": f"{spec}-24{course}/{section}",
                    "students_count": random.randint(15, 28),
                }
            )
    return groups


async def seed() -> None:
    random.seed(RANDOM_SEED)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        buildings = [Building(name=name) for name in BUILDING_NAMES]
        session.add_all(buildings)
        await session.flush()

        rooms = []
        for building in buildings:
            rooms.extend(generate_rooms(building))
        session.add_all(rooms)

        teachers = [
            Teacher(full_name=name, department=random.choice(DEPARTMENTS))
            for name in TEACHER_NAMES
        ]
        session.add_all(teachers)

        subjects = [Subject(name=name) for name in SUBJECT_NAMES]
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

        group_specs = generate_groups()
        groups = [
            StudentGroup(code=g["code"], students_count=g["students_count"], course=g["course"])
            for g in group_specs
        ]
        session.add_all(groups)

        await session.flush()  # assign ids to rooms/teachers/subjects/groups
        for spec, group in zip(group_specs, groups):
            spec["id"] = group.id

        # Cohorts: groups sharing the same specialty+course. Each cohort gets
        # 1-2 shared stream lectures (one academic_load, all cohort groups as
        # group_ids); each individual group also gets 2-3 of its own
        # practice/lab loads. Mirrors how the original hand-written seed
        # modeled the robotics lecture as a 2-group stream.
        cohorts: dict[tuple[str, int], list[dict]] = {}
        for spec in group_specs:
            cohorts.setdefault((spec["specialty"], spec["course"]), []).append(spec)

        loads: list[AcademicLoad] = []
        load_group_ids: list[list[int]] = []  # parallel to loads, filled in after flush

        for cohort_groups in cohorts.values():
            group_ids = [g["id"] for g in cohort_groups]
            for _ in range(random.randint(1, 2)):
                load = AcademicLoad(
                    subject_id=random.choice(subjects).id,
                    teacher_id=random.choice(teachers).id,
                    lesson_type="lecture",
                    total_hours_per_week=random.choice([1, 2, 2]),
                )
                loads.append(load)
                load_group_ids.append(group_ids)

            for spec in cohort_groups:
                for _ in range(random.randint(2, 3)):
                    load = AcademicLoad(
                        subject_id=random.choice(subjects).id,
                        teacher_id=random.choice(teachers).id,
                        lesson_type=random.choice(["practice", "lab"]),
                        total_hours_per_week=random.choice([1, 2]),
                    )
                    loads.append(load)
                    load_group_ids.append([spec["id"]])

        session.add_all(loads)
        await session.flush()

        load_groups = [
            AcademicLoadGroup(academic_load_id=load.id, group_id=gid)
            for load, gids in zip(loads, load_group_ids)
            for gid in gids
        ]
        session.add_all(load_groups)

        await session.commit()

    print(
        f"Seed complete: {len(buildings)} buildings, {len(rooms)} rooms, "
        f"{len(teachers)} teachers, {len(groups)} groups, {len(subjects)} subjects, "
        f"{len(time_slots)} time slots, {len(loads)} academic loads."
    )


if __name__ == "__main__":
    asyncio.run(seed())
