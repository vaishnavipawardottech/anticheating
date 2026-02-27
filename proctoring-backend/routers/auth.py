from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models.student import Student
from schemas.student import UserAuth, TokenResponse, FaceRegistrationRequest
from services.auth import hash_password, verify_password, create_access_token, create_refresh_token, get_current_user_id
from services.vision import process_and_extract_embedding, compare_faces

router = APIRouter(prefix="/api", tags=["Auth"])

@router.post("/register")
def register_student(user: UserAuth, db: Session = Depends(get_db)):
    # 1. Check if email exists
    if db.query(Student).filter(Student.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    # 2. Hash password and save to generate the ID
    new_student = Student(email=user.email, hashed_password=hash_password(user.password))
    db.add(new_student)
    db.commit()
    db.refresh(new_student) # ID is created here!

    # 3. Generate refresh token with new ID and save it
    refresh_token = create_refresh_token(data={"id": new_student.id, "email": new_student.email})
    new_student.refresh_token = refresh_token
    db.commit()

    return {"message": "Registration successful", "student_id": new_student.id}

@router.post("/login", response_model=TokenResponse)
def login_student(user: UserAuth, db: Session = Depends(get_db)):
    db_student = db.query(Student).filter(Student.email == user.email).first()
    
    if not db_student or not verify_password(user.password, db_student.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Create tokens with ID and Email in the payload
    access_token = create_access_token(data={"id": db_student.id, "email": db_student.email})
    refresh_token = create_refresh_token(data={"id": db_student.id, "email": db_student.email})

    db_student.refresh_token = refresh_token
    db.commit()

    # Check if the student already has a face registered
    face_is_registered = db_student.embedding is not None

    return {
        "access_token": access_token, 
        "refresh_token": refresh_token, 
        "token_type": "bearer",
        "has_embedding": face_is_registered # <--- Tell React!
    }

@router.post("/register-face")
def register_face(
    request: FaceRegistrationRequest, 
    student_id: int = Depends(get_current_user_id), # <--- Extracts ID automatically!
    db: Session = Depends(get_db)
):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    try:
        embedding = process_and_extract_embedding(request.image_base64)
        student.set_embedding(embedding)
        db.commit()
        return {"message": "Face verified and securely saved to your account.", "student_id": student.id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/verify-face")
def verify_live_exam_face(
    request: FaceRegistrationRequest, 
    student_id: int = Depends(get_current_user_id), 
    db: Session = Depends(get_db)
):
    # 1. Fetch the student's saved Baseline Math from the Login phase
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student or not student.embedding:
        raise HTTPException(status_code=400, detail="No registered face found. Please log in again.")

    try:
        # 2. Extract the math from the LIVE camera feed
        live_embedding = process_and_extract_embedding(request.image_base64)
        
        # 3. Compare them!
        is_match = compare_faces(student.embedding, live_embedding)
        
        if is_match:
            return {"message": "Identity verified! You may begin the exam.", "match": True}
        else:
            raise HTTPException(status_code=403, detail="Face does not match the registered student. Access Denied.")
            
    except ValueError:
         raise HTTPException(status_code=400, detail="No face detected in live feed.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))