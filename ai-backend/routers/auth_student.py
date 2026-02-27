"""
Student authentication router.
Handles login, token refresh, logout, and profile for student users.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from database.database import get_db
from database.models import Student, Department, Division, YearOfStudy
from auth.security import (
    verify_password,
    create_access_token, create_refresh_token, decode_token,
)

router = APIRouter(prefix="/auth/student", tags=["auth-student"])
security_scheme = HTTPBearer()


# ─── Schemas ───────────────────────────────────────────────────────────────────

class StudentLoginRequest(BaseModel):
    email: str
    password: str

class StudentTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    student: dict

class RefreshRequest(BaseModel):
    refresh_token: str

class StudentProfileResponse(BaseModel):
    id: int
    email: str
    full_name: str
    department: dict | None = None
    year_of_study: dict | None = None
    division: dict | None = None
    is_active: bool


# ─── Dependencies ──────────────────────────────────────────────────────────────

def get_current_student(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> Student:
    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    role = payload.get("role")
    if role != "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Student access required")

    student_id = payload.get("sub")
    student = (
        db.query(Student)
        .options(joinedload(Student.department), joinedload(Student.year_of_study), joinedload(Student.division))
        .filter(Student.id == int(student_id))
        .first()
    )
    if not student or not student.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Student not found or inactive")
    return student


def _student_dict(student: Student) -> dict:
    return {
        "id": student.id,
        "email": student.email,
        "full_name": student.full_name,
        "department": {"id": student.department.id, "name": student.department.name} if student.department else None,
        "year_of_study": {"id": student.year_of_study.id, "year": student.year_of_study.year, "label": student.year_of_study.label} if student.year_of_study else None,
        "division": {"id": student.division.id, "name": student.division.name} if student.division else None,
        "is_active": student.is_active,
        "has_photo": bool(student.face_photo_url),
        "has_embedding": bool(student.face_embedding),
        "face_photo_url": f"/uploads/{student.face_photo_url}" if student.face_photo_url else None,
    }


# ─── Routes ────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=StudentTokenResponse)
def student_login(request: StudentLoginRequest, db: Session = Depends(get_db)):
    """Authenticate student and return access + refresh tokens."""
    student = (
        db.query(Student)
        .options(joinedload(Student.department), joinedload(Student.year_of_study), joinedload(Student.division))
        .filter(Student.email == request.email)
        .first()
    )
    if not student or not verify_password(request.password, student.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if not student.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")

    access_token = create_access_token({"sub": str(student.id), "role": "student", "email": student.email})
    refresh_tok = create_refresh_token()

    student.refresh_token = refresh_tok
    db.commit()

    return StudentTokenResponse(
        access_token=access_token,
        refresh_token=refresh_tok,
        student=_student_dict(student),
    )


@router.post("/refresh", response_model=StudentTokenResponse)
def student_refresh(request: RefreshRequest, db: Session = Depends(get_db)):
    """Exchange a valid refresh token for new access + refresh tokens."""
    student = (
        db.query(Student)
        .options(joinedload(Student.department), joinedload(Student.year_of_study), joinedload(Student.division))
        .filter(Student.refresh_token == request.refresh_token)
        .first()
    )
    if not student:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    if not student.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")

    access_token = create_access_token({"sub": str(student.id), "role": "student", "email": student.email})
    new_refresh = create_refresh_token()
    student.refresh_token = new_refresh
    db.commit()

    return StudentTokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        student=_student_dict(student),
    )


@router.post("/logout")
def student_logout(student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    """Clear refresh token (server-side logout)."""
    student.refresh_token = None
    db.commit()
    return {"message": "Logged out successfully"}


@router.get("/me")
def student_me(student: Student = Depends(get_current_student)):
    """Get current student profile."""
    return _student_dict(student)
