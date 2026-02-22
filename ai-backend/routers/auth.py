"""
Authentication router for teacher login.
JWT stored in localStorage on the frontend, sent as Bearer token.
Refresh token stored in DB (teachers.refresh_token) and cleared on logout.
"""

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt as _bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import Teacher

# ─── Config ───────────────────────────────────────────────────────────────────

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "pareeksha-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24 * 7   # 7 days — stays logged in across restarts

# ─── Crypto helpers ───────────────────────────────────────────────────────────

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# ─── Pydantic schemas ─────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TeacherOut(BaseModel):
    id: int
    email: str
    full_name: str
    is_admin: bool
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None  # stored in DB and optionally in client
    token_type: str = "bearer"
    teacher: TeacherOut


class RefreshRequest(BaseModel):
    refresh_token: str


class CreateTeacherRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    is_admin: bool = False


# ─── Auth dependency ──────────────────────────────────────────────────────────

def get_current_teacher(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Teacher:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        teacher_id = int(sub) if isinstance(sub, str) else sub
    except (JWTError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid token")

    teacher = db.query(Teacher).filter(
        Teacher.id == teacher_id, Teacher.is_active == True
    ).first()
    if not teacher:
        raise HTTPException(status_code=401, detail="Teacher not found or inactive")
    return teacher


def require_admin(current: Teacher = Depends(get_current_teacher)) -> Teacher:
    if not current.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current


# ─── Router ───────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/auth", tags=["auth"])


def _generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    teacher = db.query(Teacher).filter(Teacher.email == payload.email).first()
    if not teacher or not verify_password(payload.password, teacher.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not teacher.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")

    access_token = create_access_token({"sub": str(teacher.id)})
    refresh_token = _generate_refresh_token()
    teacher.refresh_token = refresh_token
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        teacher=TeacherOut.model_validate(teacher),
    )


@router.get("/me", response_model=TeacherOut)
def get_me(current: Teacher = Depends(get_current_teacher)):
    return TeacherOut.model_validate(current)


@router.get("/teachers", response_model=list[TeacherOut])
def list_teachers(
    _: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    return db.query(Teacher).filter(Teacher.is_active == True).order_by(Teacher.full_name).all()


@router.post("/refresh", response_model=LoginResponse)
def refresh_tokens(payload: RefreshRequest, db: Session = Depends(get_db)):
    """Exchange a valid refresh_token for a new access_token (and new refresh_token). Use after reload when access_token is expired."""
    teacher = db.query(Teacher).filter(
        Teacher.refresh_token == payload.refresh_token,
        Teacher.is_active == True,
    ).first()
    if not teacher or not teacher.refresh_token:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    access_token = create_access_token({"sub": str(teacher.id)})
    new_refresh = _generate_refresh_token()
    teacher.refresh_token = new_refresh
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return LoginResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        teacher=TeacherOut.model_validate(teacher),
    )


@router.post("/logout")
def logout(current: Teacher = Depends(get_current_teacher), db: Session = Depends(get_db)):
    """Clear refresh_token for this teacher so the session is revoked server-side."""
    current.refresh_token = None
    db.add(current)
    db.commit()
    return {"detail": "Logged out"}


@router.post("/teachers", response_model=TeacherOut, status_code=201)
def create_teacher(
    payload: CreateTeacherRequest,
    _admin: Teacher = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if db.query(Teacher).filter(Teacher.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    teacher = Teacher(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        is_admin=payload.is_admin,
    )
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return TeacherOut.model_validate(teacher)
