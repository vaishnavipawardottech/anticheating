"""
Smart Assessment API — Main Application
FastAPI application for the Smart Assessment system.
Manages academic structure, document ingestion, question generation, and MCQ examinations.
"""

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os

from database.database import engine, Base, SessionLocal
from database.models import Teacher, Department, Division, YearOfStudy
from auth.security import hash_password

from routers import (
    subjects, units, concepts, structure_ai,
    documents, cleanup, alignment, documents_db,
    search, context, exams, questions, generation,
    auth_teacher, auth_student, mcq_pool, mcq_exam, mcq_student,
    proctoring,
)
from routers import auth as auth_admin


def _seed_defaults():
    """Create default admin, departments, divisions, and years if they don't exist."""
    db = SessionLocal()
    try:
        # Seed admin teacher
        if db.query(Teacher).count() == 0:
            admin = Teacher(
                email="admin@org.com",
                hashed_password=hash_password("admin"),
                full_name="Admin",
                is_admin=True,
                is_active=True,
            )
            db.add(admin)
            db.commit()
            print("✓ Default admin teacher created: admin@org.com / admin")

        # Seed default years of study
        if db.query(YearOfStudy).count() == 0:
            for year, label in [(1, "FE"), (2, "SE"), (3, "TE"), (4, "BE")]:
                db.add(YearOfStudy(year=year, label=label))
            db.commit()
            print("✓ Default years of study seeded (FE, SE, TE, BE)")

        # Seed default divisions
        if db.query(Division).count() == 0:
            for name in ["A", "B", "C"]:
                db.add(Division(name=name))
            db.commit()
            print("✓ Default divisions seeded (A, B, C)")

    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables + seed defaults."""
    Base.metadata.create_all(bind=engine)
    _seed_defaults()
    # Ensure uploads directory exists
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads", "photos"), exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads", "snapshots"), exist_ok=True)
    yield


app = FastAPI(
    title="Smart Assessment API",
    description="Academic structure, document ingestion, question generation, and MCQ examination system",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ───────────────────────────────────────────────────────────────────

# Auth
app.include_router(auth_admin.router)        # /auth/* (backward-compat login + admin CRUD)
app.include_router(auth_teacher.router)       # /auth/teacher/*
app.include_router(auth_student.router)       # /auth/student/*

# Academic structure
app.include_router(subjects.router)
app.include_router(units.router)
app.include_router(concepts.router)
app.include_router(structure_ai.router)

# Document ingestion
app.include_router(documents_db.router)
app.include_router(documents.router)
app.include_router(cleanup.router)
app.include_router(alignment.router)
app.include_router(search.router)
app.include_router(context.router)

# Question generation
app.include_router(exams.router)
app.include_router(questions.router)
app.include_router(generation.router)

# MCQ examination system
app.include_router(mcq_pool.router)           # /mcq-pool/*
app.include_router(mcq_exam.router)           # /mcq-exams/*
app.include_router(mcq_student.router)        # /student/exams/*
app.include_router(proctoring.router)          # /student/photo/*, /student/exams/*/proctoring-event

# Static files — serve uploaded photos and snapshots
uploads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")


@app.get("/")
def root():
    return {
        "name": "Smart Assessment API",
        "version": "2.0.0",
        "endpoints": {
            "docs": "/docs",
            "auth": "/auth",
            "subjects": "/subjects",
            "mcq_pool": "/mcq-pool",
            "mcq_exams": "/mcq-exams",
            "student_exams": "/student/exams",
        },
    }


@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "smart-assessment-api"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
