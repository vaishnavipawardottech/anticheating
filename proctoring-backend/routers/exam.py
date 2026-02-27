from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import get_db
from models.student import Student
from services.auth import get_current_user
from services.tasks import save_event_to_db
from services.vision import process_and_extract_embedding, compare_faces

router = APIRouter(prefix="/api/exam", tags=["Exam"])

class EventRequest(BaseModel):
    event_type: str
    details: str = ""
    snapshot_base64: Optional[str] = None

class ContinuousVerifyRequest(BaseModel):
    image_base64: str

@router.post("/log-event")
def log_student_event(
    request: EventRequest, 
    user: dict = Depends(get_current_user)
):
    # Because of the @huey_queue.task() decorator, this doesn't run the function.
    # Instead, it instantly packages it and sends it to Valkey!
    save_event_to_db(
        user["id"],
        request.event_type,
        request.details,
        request.snapshot_base64
    )
    
    return {"status": "Event queued to Valkey successfully"}

@router.post("/continuous-verify")
def continuous_identity_check(
    request: ContinuousVerifyRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Continuously verify identity during exam using ArcFace embeddings"""
    print(f"🔍 Continuous identity check for student ID: {user['id']}")
    
    student = db.query(Student).filter(Student.id == user["id"]).first()
    if not student or not student.embedding:
        print(f"❌ No registered face found for student {user['id']}")
        raise HTTPException(status_code=400, detail="No registered face found")

    try:
        print("📸 Extracting embedding from live snapshot...")
        # Use enforce_detection=False for continuous checks to handle temporary face detection failures gracefully
        live_embedding = process_and_extract_embedding(request.image_base64, enforce_detection=False)
        
        # If no face detected in this frame, skip verification but don't count as mismatch
        if live_embedding is None:
            print("⚠️ No clear face in frame - skipping this verification cycle")
            return {
                "match": True,  # Don't penalize for temporary detection failures
                "skipped": True,
                "message": "No clear face detected in frame - please face the camera"
            }
        
        print("🔄 Comparing embeddings...")
        is_match = compare_faces(student.embedding, live_embedding)
        
        result = "✅ MATCH" if is_match else "❌ MISMATCH"
        print(f"{result} - Identity verification result: {is_match}")
        
        return {
            "match": is_match,
            "skipped": False,
            "message": "Identity verified" if is_match else "Identity mismatch detected"
        }
    except Exception as e:
        print(f"❌ Identity verification error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))