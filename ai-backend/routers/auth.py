"""
Admin authentication & management router.
Admin (teacher with is_admin=True) can manage teachers, students, departments, divisions, years.
Also provides backward-compatible /auth/login, /auth/refresh, /auth/logout endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel
from typing import Optional, List

from database.database import get_db
from database.models import Teacher, Student, Department, Division, YearOfStudy
from auth.security import hash_password, verify_password, create_access_token, create_refresh_token, decode_token
from routers.auth_teacher import get_current_teacher, require_admin

router = APIRouter(prefix="/auth", tags=["auth-admin"])


# ─── Schemas ───────────────────────────────────────────────────────────────────

class CreateTeacherRequest(BaseModel):
    email: str
    full_name: str
    password: str
    is_admin: bool = False

class CreateStudentRequest(BaseModel):
    email: str
    full_name: str
    password: str
    department_id: Optional[int] = None
    year_id: Optional[int] = None
    division_id: Optional[int] = None

class DepartmentCreate(BaseModel):
    name: str

class DivisionCreate(BaseModel):
    name: str

class YearCreate(BaseModel):
    year: int
    label: str

# Backward-compatible login schemas
class LoginRequest(BaseModel):
    email: str
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str


# ─── Backward-compatible auth routes (for existing frontend) ──────────────────

@router.post("/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Backward-compatible login (teacher-only, same response as auth_teacher)."""
    teacher = db.query(Teacher).filter(Teacher.email == request.email).first()
    if not teacher or not verify_password(request.password, teacher.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not teacher.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")

    access_token = create_access_token({"sub": str(teacher.id), "role": "teacher", "email": teacher.email})
    refresh_tok = create_refresh_token()
    teacher.refresh_token = refresh_tok
    db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_tok,
        "token_type": "bearer",
        "teacher": {
            "id": teacher.id, "email": teacher.email,
            "full_name": teacher.full_name, "is_admin": teacher.is_admin,
            "is_active": teacher.is_active,
        },
    }

@router.post("/refresh")
def refresh(request: RefreshRequest, db: Session = Depends(get_db)):
    """Backward-compatible refresh (teacher-only)."""
    teacher = db.query(Teacher).filter(Teacher.refresh_token == request.refresh_token).first()
    if not teacher:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    if not teacher.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")

    access_token = create_access_token({"sub": str(teacher.id), "role": "teacher", "email": teacher.email})
    new_refresh = create_refresh_token()
    teacher.refresh_token = new_refresh
    db.commit()

    return {
        "access_token": access_token, "refresh_token": new_refresh, "token_type": "bearer",
        "teacher": {
            "id": teacher.id, "email": teacher.email,
            "full_name": teacher.full_name, "is_admin": teacher.is_admin,
            "is_active": teacher.is_active,
        },
    }

@router.post("/logout")
def logout(teacher: Teacher = Depends(get_current_teacher), db: Session = Depends(get_db)):
    """Backward-compatible logout."""
    teacher.refresh_token = None
    db.commit()
    return {"message": "Logged out successfully"}


# ─── Teacher management (admin only) ──────────────────────────────────────────

@router.post("/teachers", status_code=status.HTTP_201_CREATED)
def create_teacher(request: CreateTeacherRequest, admin: Teacher = Depends(require_admin), db: Session = Depends(get_db)):
    """Create a new teacher account (admin only)."""
    existing = db.query(Teacher).filter(Teacher.email == request.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    teacher = Teacher(
        email=request.email,
        full_name=request.full_name,
        hashed_password=hash_password(request.password),
        is_admin=request.is_admin,
    )
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return {"id": teacher.id, "email": teacher.email, "full_name": teacher.full_name, "is_admin": teacher.is_admin, "is_active": teacher.is_active}


@router.get("/teachers")
def list_teachers(teacher: Teacher = Depends(get_current_teacher), db: Session = Depends(get_db)):
    """List all teachers."""
    teachers = db.query(Teacher).order_by(Teacher.id).all()
    return [
        {"id": t.id, "email": t.email, "full_name": t.full_name, "is_admin": t.is_admin, "is_active": t.is_active}
        for t in teachers
    ]


# ─── Student management (admin only) ──────────────────────────────────────────

@router.post("/students", status_code=status.HTTP_201_CREATED)
def create_student(request: CreateStudentRequest, admin: Teacher = Depends(require_admin), db: Session = Depends(get_db)):
    """Create a new student account (admin only)."""
    existing = db.query(Student).filter(Student.email == request.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    student = Student(
        email=request.email,
        full_name=request.full_name,
        hashed_password=hash_password(request.password),
        department_id=request.department_id,
        year_id=request.year_id,
        division_id=request.division_id,
    )
    db.add(student)
    db.commit()
    db.refresh(student)

    # Reload with relationships
    student = (
        db.query(Student)
        .options(joinedload(Student.department), joinedload(Student.year_of_study), joinedload(Student.division))
        .filter(Student.id == student.id).first()
    )

    return {
        "id": student.id, "email": student.email, "full_name": student.full_name,
        "department": {"id": student.department.id, "name": student.department.name} if student.department else None,
        "year_of_study": {"id": student.year_of_study.id, "year": student.year_of_study.year, "label": student.year_of_study.label} if student.year_of_study else None,
        "division": {"id": student.division.id, "name": student.division.name} if student.division else None,
        "is_active": student.is_active,
    }


@router.get("/students")
def list_students(
    department_id: Optional[int] = None,
    year_id: Optional[int] = None,
    division_id: Optional[int] = None,
    teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """List students with optional filters."""
    q = db.query(Student).options(
        joinedload(Student.department), joinedload(Student.year_of_study), joinedload(Student.division)
    )
    if department_id:
        q = q.filter(Student.department_id == department_id)
    if year_id:
        q = q.filter(Student.year_id == year_id)
    if division_id:
        q = q.filter(Student.division_id == division_id)

    students = q.order_by(Student.id).all()
    return [
        {
            "id": s.id, "email": s.email, "full_name": s.full_name,
            "department": {"id": s.department.id, "name": s.department.name} if s.department else None,
            "year_of_study": {"id": s.year_of_study.id, "year": s.year_of_study.year, "label": s.year_of_study.label} if s.year_of_study else None,
            "division": {"id": s.division.id, "name": s.division.name} if s.division else None,
            "is_active": s.is_active,
        }
        for s in students
    ]


# ─── Department / Division / Year CRUD ─────────────────────────────────────────

@router.get("/departments")
def list_departments(db: Session = Depends(get_db)):
    return [{"id": d.id, "name": d.name} for d in db.query(Department).order_by(Department.name).all()]

@router.post("/departments", status_code=201)
def create_department(data: DepartmentCreate, admin: Teacher = Depends(require_admin), db: Session = Depends(get_db)):
    if db.query(Department).filter(Department.name == data.name).first():
        raise HTTPException(status_code=400, detail="Department already exists")
    dept = Department(name=data.name)
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return {"id": dept.id, "name": dept.name}

@router.delete("/departments/{dept_id}", status_code=204)
def delete_department(dept_id: int, admin: Teacher = Depends(require_admin), db: Session = Depends(get_db)):
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    db.delete(dept)
    db.commit()

@router.get("/divisions")
def list_divisions(db: Session = Depends(get_db)):
    return [{"id": d.id, "name": d.name} for d in db.query(Division).order_by(Division.name).all()]

@router.post("/divisions", status_code=201)
def create_division(data: DivisionCreate, admin: Teacher = Depends(require_admin), db: Session = Depends(get_db)):
    if db.query(Division).filter(Division.name == data.name).first():
        raise HTTPException(status_code=400, detail="Division already exists")
    div = Division(name=data.name)
    db.add(div)
    db.commit()
    db.refresh(div)
    return {"id": div.id, "name": div.name}

@router.delete("/divisions/{div_id}", status_code=204)
def delete_division(div_id: int, admin: Teacher = Depends(require_admin), db: Session = Depends(get_db)):
    div = db.query(Division).filter(Division.id == div_id).first()
    if not div:
        raise HTTPException(status_code=404, detail="Division not found")
    db.delete(div)
    db.commit()

@router.get("/years")
def list_years(db: Session = Depends(get_db)):
    return [{"id": y.id, "year": y.year, "label": y.label} for y in db.query(YearOfStudy).order_by(YearOfStudy.year).all()]

@router.post("/years", status_code=201)
def create_year(data: YearCreate, admin: Teacher = Depends(require_admin), db: Session = Depends(get_db)):
    if db.query(YearOfStudy).filter(YearOfStudy.year == data.year).first():
        raise HTTPException(status_code=400, detail="Year already exists")
    yr = YearOfStudy(year=data.year, label=data.label)
    db.add(yr)
    db.commit()
    db.refresh(yr)
    return {"id": yr.id, "year": yr.year, "label": yr.label}

@router.delete("/years/{year_id}", status_code=204)
def delete_year(year_id: int, admin: Teacher = Depends(require_admin), db: Session = Depends(get_db)):
    yr = db.query(YearOfStudy).filter(YearOfStudy.id == year_id).first()
    if not yr:
        raise HTTPException(status_code=404, detail="Year not found")
    db.delete(yr)
    db.commit()
