# Smart Manual Timetable System — дизайн MVP

Дата: 2026-09-14. Источник требований: ТЗ от Amir (14.09.2026 13:30).
Отступления от ТЗ собраны в разделе «Отступления» в конце.

## Цель

Ручное составление университетского расписания: диспетчер перетаскивает
карточки нагрузки в сетку «дни × пары», система сразу показывает конфликты
и помогает выбрать аудиторию. Автоматической генерации расписания нет.

Готово, когда: `python seed.py`, `uvicorn main:app --reload`, `npm run dev` —
и в браузере можно расставить всю нагрузку из seed, видя ошибки и
предупреждения, без правок кода.

## Стек

- Backend: Python 3.11+, FastAPI, SQLAlchemy 2 (async, aiosqlite), Pydantic v2, SQLite.
- Frontend: Vue 3 (`<script setup>`, plain JS), Vite, Tailwind CSS v4 (`@tailwindcss/vite`),
  Pinia, Axios, нативный HTML5 Drag and Drop.

## Структура

```
timetable-system/
  backend/
    database/models.py     9 таблиц, engine, async_sessionmaker
    main.py                FastAPI: схемы, find_conflicts, 4 эндпоинта
    seed.py                drop_all + create_all + данные
    test_validation.py     assert-проверки правил, `python test_validation.py`
    requirements.txt
  frontend/
    vite.config.js         vue + tailwind плагины, proxy /api -> http://127.0.0.1:8000
    src/main.js, src/style.css, src/App.vue
    src/stores/schedule.js
    src/components/LoadPool.vue
    src/components/ScheduleGrid.vue
    src/components/RoomPickerModal.vue
  README.md
```

CORS не настраивается: фронтенд ходит на `/api` через Vite proxy.

## База данных (`backend/database/models.py`)

| Таблица | Поля |
|---|---|
| buildings | id, name |
| rooms | id, building_id FK, number, capacity int, is_lab bool, floor int |
| teachers | id, full_name, department |
| student_groups | id, code, students_count int, course int |
| subjects | id, name |
| time_slots | id, slot_number 1..6, start_time str, end_time str |
| academic_loads | id, subject_id FK, teacher_id FK, lesson_type `lecture`/`practice`/`lab`, total_hours_per_week int |
| academic_load_groups | academic_load_id FK, group_id FK (составной PK) |
| schedule_items | id, academic_load_id FK, room_id FK, time_slot_id FK, day_of_week int 1..6 |

- `schedule_items`: `UniqueConstraint(room_id, day_of_week, time_slot_id)` — двойная
  бронь аудитории невозможна даже при гонке запросов.
- БД — файл `backend/timetable.db`. `main.py` на старте делает `create_all`
  (приложение поднимается и без seed, просто пустое).

### Единица нагрузки

1 размещённая пара (`schedule_item`) = 1 час из `total_hours_per_week`.
Пара длится 50 минут, перемена 10 минут.
Остаток карточки: `total_hours_per_week − count(schedule_items этой карточки)`.

## Валидация

Одна функция `find_conflicts(session, load, day, time_slot_id, room_id | None, current_item_id | None)`
возвращает `(errors: list[str], warnings: list[str])`. Все проверки игнорируют
пару с `id == current_item_id` (перенос не конфликтует сам с собой).

Размер потока = сумма `students_count` всех групп карточки.

### Ошибки — ставить нельзя

- **a) Аудитория занята**: есть пара с тем же room, day, slot.
  «Аудитория 3/509 занята: Робототехника и IoT (ИС-242/1)».
- **b) Преподаватель занят**: есть пара карточки с тем же teacher_id в этот day/slot.
  «Шаяхметов И. уже ведёт пару в аудитории 2/201».
- **c) Группа занята**: любая группа карточки состоит в карточке пары в этот day/slot.
  По одному сообщению на группу: «ИС-242/1 уже на паре: Базы данных».

### Предупреждения — ставить можно

- **d) Мало мест**: `room.capacity < размер потока`.
  «Вместимость 25 < 47 студентов — не хватит 22 мест».
- **Лаба без оборудования**: `lesson_type == "lab"` и `not room.is_lab`.
  «Лабораторная в аудитории без оборудования».

### Проверка без `room_id` (подсветка ячейки при перетаскивании)

Проверяются b и c. Затем по свободным в этот day/slot аудиториям:
- нет ни одной свободной → ошибка «Нет свободных аудиторий в этот слот»;
- свободные есть, но у каждой есть предупреждение → одно предупреждение
  с лучшим вариантом: «Нет подходящей аудитории на 47 мест, самая большая
  свободная — 2/201 (40)» (для лабы — «Нет свободной лаборатории»);
- есть свободная без предупреждений → ни ошибок, ни предупреждений.

`is_valid = len(errors) == 0`.

## API (`backend/main.py`)

### `GET /api/initial-data`

```json
{
  "buildings": [{"id", "name"}],
  "rooms": [{"id", "building_id", "building_name", "number", "capacity", "is_lab", "floor"}],
  "teachers": [{"id", "full_name", "department"}],
  "groups": [{"id", "code", "students_count", "course"}],
  "subjects": [{"id", "name"}],
  "time_slots": [{"id", "slot_number", "start_time", "end_time"}],
  "loads": [{"id", "subject_id", "teacher_id", "lesson_type", "total_hours_per_week", "group_ids", "students_total"}],
  "items": [{"id", "academic_load_id", "room_id", "time_slot_id", "day_of_week"}]
}
```

### `POST /api/schedule/validate`

Запрос: `{academic_load_id: int, day_of_week: int (1..6), time_slot_id: int, room_id: int | null, current_item_id: int | null}`.
Ответ `200`: `{is_valid: bool, errors: string[], warnings: string[]}`.
Несуществующая карточка/слот/аудитория/пара → `404`. `day_of_week` вне 1..6 → `422` (Pydantic).

### `POST /api/schedule/assign`

Тот же запрос, `room_id` обязателен (`422` без него).
1. `find_conflicts`; при ошибках → `409` с телом `{is_valid: false, errors, warnings}`.
2. Если `current_item_id` не задан и остаток карточки ≤ 0 → `409`, ошибка «Все часы уже расставлены».
3. `current_item_id` задан → обновить эту пару (её `academic_load_id` должен совпадать, иначе `400`);
   иначе создать новую.
4. `IntegrityError` от UniqueConstraint → `409` «Аудитория занята».
5. Ответ `200`: созданная/обновлённая пара + `warnings`.

### `DELETE /api/schedule/unassign/{id}`

`204`, либо `404`, если пары нет.

## Seed (`backend/seed.py`)

Пересоздаёт все таблицы и заполняет:
- 1 корпус «Главный корпус».
- 6 слотов: 08:00–08:50, 09:00–09:50, 10:00–10:50, 11:00–11:50, 12:00–12:50, 13:00–13:50.
- 5 аудиторий, вместимость 15–60, из них 2 лаборатории; самая большая — 60,
  следующая по размеру — меньше 47 (чтобы поток был виден).
- 3 преподавателя (включая «Шаяхметов И.»), 4 группы по 18–25 студентов (включая «ИС-242/1»).
- Предметы, включая «Робототехника и IoT».
- 8 карточек нагрузки всех трёх типов, в том числе лекция-поток на 2 группы
  суммарно 47 студентов. Суммарные часы помещаются в сетку 6×6 без неизбежных конфликтов.
- `schedule_items` пустые.

## Фронтенд

### Разметка (`App.vue`)

- Шапка: переключатель режима «По группам / По аудиториям / По преподавателям»
  и `<select>` конкретной сущности (по умолчанию первая в списке; при смене
  режима выбор сбрасывается на первую).
- Слева `LoadPool`, справа `ScheduleGrid`, поверх — `RoomPickerModal`, когда открыт.
- Если `initial-data` не загрузился — красная плашка
  «Бэкенд недоступен — запустите uvicorn (см. README)».
- Ошибка `assign`/`unassign` показывается текстом в той же плашке.

### Store (`stores/schedule.js`, Pinia)

- state: данные `initial-data`, `viewMode` (`group`/`room`/`teacher`), `selectedId`,
  `dragging: {loadId, itemId | null} | null`, `cellCache: Map<"day-slot", result>`, `error`.
- `remaining(loadId)`.
- `poolLoads`: карточки с остатком > 0; в режимах group/teacher — только карточки
  выбранной группы/преподавателя, в режиме room — все.
- `itemAt(day, slotId)`: пара выбранной сущности в ячейке (не больше одной по правилам a/b/c).
- `validateCell(day, slotId)`: `validate` без `room_id`, результат кэшируется в `cellCache`;
  повторный запрос на ту же ячейку во время одного перетаскивания не уходит.
- `validateRoom(day, slotId, roomId)`: `validate` с `room_id`, без кэша.
- `assign(payload)`, `unassign(id)`: запрос, затем `load()` заново.
- `startDrag(...)` / `endDrag()` — `endDrag` очищает `dragging` и `cellCache`.

### Пул (`LoadPool.vue`)

Карточка `draggable="true"`: предмет, метка типа (Лекция / Практика / Лаб, разные цвета),
преподаватель, коды групп, число студентов, «осталось N из M».
Пустой пул — «Вся нагрузка расставлена».

### Сетка (`ScheduleGrid.vue`)

- Строки — слоты («1 пара 08:00–08:50»), столбцы — Пн…Сб.
- Пара в ячейке: предмет, метка типа, аудитория, плюс преподаватель (режимы group/room)
  или группы (режим teacher). `draggable` (перенос, передаёт `itemId`) и кнопка ×
  (`unassign`).
- Во время перетаскивания над ячейкой: `validateCell`, рамка
  - зелёная — `is_valid` и нет предупреждений;
  - жёлтая — `is_valid` и есть предупреждения;
  - красная — `!is_valid`;
  - серая пунктирная — пока ответ не пришёл.
- Тултип — свой абсолютный блок у ячейки под курсором со списком ошибок/предупреждений
  (нативный `title` во время drag не показывается).
- `drop`: на красную ничего; на зелёную/жёлтую — открыть модалку с `{loadId, itemId, day, slotId}`.

### Модалка (`RoomPickerModal.vue`)

- Заголовок: предмет, день, пара, размер потока.
- `Promise.all` на `validateRoom` для всех аудиторий.
- Сортировка:
  1. зелёные (без ошибок и предупреждений) — по возрастанию `capacity − размер потока`;
  2. жёлтые (только предупреждения) — по убыванию `capacity`; текст предупреждений на строке;
  3. красные (ошибки) — `disabled`, текст ошибки на строке.
- Строка: номер, корпус, этаж, вместимость, значок «Лаб».
- Клик по зелёной/жёлтой → `assign` → закрыть. Кнопка «Отмена» и Esc закрывают.

## Проверка

- `backend/test_validation.py`: in-memory SQLite, свои мини-данные, `assert` на
  a, b, c (ошибки), d и лабу (предупреждения), `current_item_id` (перенос сам с собой
  не конфликтует), проверку без `room_id` (ошибка / предупреждение / чисто).
  Запуск `python test_validation.py`, печатает `OK`.
- Ручной сценарий в браузере после запуска:
  1. поток на 47 студентов над ячейкой → жёлтая рамка, тултип про аудиторию;
  2. drop → в модалке сверху аудитория на 60, затем жёлтые меньшие, после её
     назначения другой парой в тот же слот — она красная;
  3. вторая пара той же группы в тот же слот → красная ячейка, тултип с правилом c;
  4. × на паре → карточка возвращается в пул, остаток часов растёт;
  5. перенос пары в другую ячейку.
- `npm run build` проходит без ошибок.

## README

Требования (Python 3.11+, Node 18+), затем по шагам:
- backend: `cd backend`, `python -m venv .venv`, активация (Windows и macOS/Linux),
  `pip install -r requirements.txt`, `python seed.py`, `uvicorn main:app --reload`;
- frontend: `cd frontend`, `npm install`, `npm run dev`, открыть `http://localhost:5173`;
- запуск теста.

## Отступления от ТЗ

1. **Правило d — предупреждение, а не ошибка.** Если подходящей аудитории нет,
   пользователь может выбрать свободную меньшую и видит, в чём проблема
   (решение пользователя).
2. **Добавлено предупреждение «лабораторная в аудитории без оборудования».**
3. **`room_id` в `/validate` необязателен** — иначе подсветку при перетаскивании
   (до выбора аудитории) нечем проверять.
4. **Ответ `/validate` содержит `warnings`** помимо `is_valid` и `errors`.
5. **`/assign` проверяет остаток часов** — иначе через API можно поставить больше пар, чем в нагрузке.
6. **`/assign` с `current_item_id` переносит пару**, а не создаёт новую.
7. **`/initial-data` дополнительно отдаёт buildings и subjects** — нужны для отображения.

## Вне рамок

Авторизация, миграции (Alembic), автогенерация расписания, чётные/нечётные недели,
несколько корпусов с учётом переходов, экспорт.
