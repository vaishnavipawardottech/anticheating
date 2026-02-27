"""
Teacher authentication router.
Handles login, token refresh, logout, and profile for teacher users.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional

from database.database import get_db
from database.models import Teacher
from auth.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
)

router = APIRouter(prefix="/auth/teacher", tags=["auth-teacher"])


# ─── Schemas ───────────────────────────────────────────────────────────────────

class TeacherLoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    teacher: dict

class RefreshRequest(BaseModel):
    refresh_token: str

class TeacherProfileResponse(BaseModel):
    id: int
    email: str
    full_name: str
    is_admin: bool
    is_active: bool

    class Config:
        from_attributes = True


# ─── Dependencies ──────────────────────────────────────────────────────────────

def get_current_teacher(db: Session = Depends(get_db)) -> "TeacherDep":
    """FastAPI dependency – extracts teacher from JWT in Authorization header."""
    from fastapi import Request
    # This will be used as a sub-dependency
    pass

# We use a closure-based dependency to avoid circular import issues
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security_scheme = HTTPBearer()


def get_current_teacher(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> Teacher:
    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    role = payload.get("role")
    if role != "teacher":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Teacher access required")

    teacher_id = payload.get("sub")
    teacher = db.query(Teacher).filter(Teacher.id == int(teacher_id)).first()
    if not teacher or not teacher.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Teacher not found or inactive")
    return teacher


def require_admin(teacher: Teacher = Depends(get_current_teacher)) -> Teacher:
    if not teacher.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return teacher


# ─── Routes ────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
def teacher_login(request: TeacherLoginRequest, db: Session = Depends(get_db)):
    """Authenticate teacher and return access + refresh tokens."""
    teacher = db.query(Teacher).filter(Teacher.email == request.email).first()
    if not teacher or not verify_password(request.password, teacher.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if not teacher.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")

    access_token = create_access_token({"sub": str(teacher.id), "role": "teacher", "email": teacher.email})
    refresh_tok = create_refresh_token()

    teacher.refresh_token = refresh_tok
    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_tok,
        teacher={
            "id": teacher.id,
            "email": teacher.email,
            "full_name": teacher.full_name,
            "is_admin": teacher.is_admin,
            "is_active": teacher.is_active,
        },
    )


@router.post("/refresh", response_model=TokenResponse)
def teacher_refresh(request: RefreshRequest, db: Session = Depends(get_db)):
    """Exchange a valid refresh token for new access + refresh tokens."""
    teacher = db.query(Teacher).filter(Teacher.refresh_token == request.refresh_token).first()
    if not teacher:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    if not teacher.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")

    access_token = create_access_token({"sub": str(teacher.id), "role": "teacher", "email": teacher.email})
    new_refresh = create_refresh_token()
    teacher.refresh_token = new_refresh
    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        teacher={
            "id": teacher.id,
            "email": teacher.email,
            "full_name": teacher.full_name,
            "is_admin": teacher.is_admin,
            "is_active": teacher.is_active,
        },
    )


@router.post("/logout")
def teacher_logout(teacher: Teacher = Depends(get_current_teacher), db: Session = Depends(get_db)):
    """Clear refresh token (server-side logout)."""
    teacher.refresh_token = None
    db.commit()
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=TeacherProfileResponse)
def teacher_me(teacher: Teacher = Depends(get_current_teacher)):
    """Get current teacher profile."""
    return teacher
