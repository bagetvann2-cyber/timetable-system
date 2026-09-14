"""App entrypoint: creates the FastAPI app, wires up CORS and the DB
lifecycle, and mounts the two routers. No business logic lives here —
see schedule_routes.py (board/validate/assign/unassign/auto-generate),
references.py (CRUD for buildings/rooms/teachers/groups/subjects/
time_slots/loads), validation.py (the 4-rule engine), and scheduler.py
(the auto-generate algorithm).

See docs/superpowers/specs/2026-09-14-timetable-system-design.md for the
business rules this implements.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database.models import init_db
from references import router as references_router
from schedule_routes import router as schedule_router


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

app.include_router(schedule_router)
app.include_router(references_router)
