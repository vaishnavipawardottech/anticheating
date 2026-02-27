"""
Proctoring router.
Student-facing endpoints for face registration, verification, photo upload,
and proctoring event logging during MCQ exams.

Ported from anticheating-main/proctoring-backend/routers/auth.py + routers/exam.py
"""

import os
import base64
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from database.database import get_db
from database.models import Student, McqStudentExamInstance, ProctoringEvent
from routers.auth_student import get_current_student

router = APIRouter(tags=["proctoring"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")


# ─── Schemas ───────────────────────────────────────────────────────────────────

class ProctoringEventRequest(BaseModel):
    event_type: str
    details: str = ""
    snapshot_base64: Optional[str] = None

class FaceRegistrationRequest(BaseModel):
    image_base64: str  # Base64 encoded webcam screenshot

class ContinuousVerifyRequest(BaseModel):
    image_base64: str


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _save_snapshot(snapshot_base64: str, instance_id: int) -> Optional[str]:
    """Save a base64 snapshot to uploads/snapshots/{instance_id}/{timestamp}.jpg. Returns relative path."""
    if not snapshot_base64 or not snapshot_base64.strip():
        return None

    try:
        if "," in snapshot_base64:
            snapshot_base64 = snapshot_base64.split(",", 1)[1]

        snapshots_dir = os.path.join(UPLOAD_DIR, "snapshots", str(instance_id))
        os.makedirs(snapshots_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        filename = f"{timestamp}.jpg"
        relative_path = f"snapshots/{instance_id}/{filename}"
        absolute_path = os.path.join(UPLOAD_DIR, relative_path)

        decoded_data = base64.b64decode(snapshot_base64)
        with open(absolute_path, "wb") as f:
            f.write(decoded_data)

        return relative_path
    except Exception as e:
        print(f"❌ Error saving snapshot: {e}")
        return None


# ─── Routes: Face Registration & Verification ─────────────────────────────────

@router.post("/student/register-face")
def register_face(
    request: FaceRegistrationRequest,
    student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """
    Register a student's face. Takes a webcam base64 screenshot,
    extracts ArcFace 512-dim embedding, and stores it in the DB.
    """
    from services.face_service import process_and_extract_embedding

    try:
        print(f"📸 Extracting face embedding for student {student.id}...")
        embedding = process_and_extract_embedding(request.image_base64, enforce_detection=True)
        student.face_embedding = embedding

        # Also save the image as the face photo
        if "," in request.image_base64:
            img_data = request.image_base64.split(",", 1)[1]
        else:
            img_data = request.image_base64

        photos_dir = os.path.join(UPLOAD_DIR, "photos")
        os.makedirs(photos_dir, exist_ok=True)
        filename = f"{student.id}.jpg"
        filepath = os.path.join(photos_dir, filename)
        with open(filepath, "wb") as f:
            f.write(base64.b64decode(img_data))

        student.face_photo_url = f"photos/{filename}"
        db.commit()
        print(f"✅ Face registered for student {student.id}")

        return {
            "message": "Face verified and securely saved to your account.",
            "student_id": student.id,
            "photo_url": f"/uploads/photos/{filename}",
        }
    except Exception as e:
        print(f"❌ Face registration error: {e}")
        raise HTTPException(status_code=400, detail=f"Face registration failed: {str(e)}")


@router.post("/student/verify-face")
def verify_face(
    request: FaceRegistrationRequest,
    student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """
    Verify a student's identity before exam start.
    Compares live webcam screenshot against stored embedding.
    """
    from services.face_service import process_and_extract_embedding, compare_faces

    if not student.face_embedding:
        raise HTTPException(status_code=400, detail="No registered face found. Please register your face first.")

    try:
        print(f"🔍 Verifying identity for student {student.id}...")
        live_embedding = process_and_extract_embedding(request.image_base64, enforce_detection=True)

        is_match = compare_faces(student.face_embedding, live_embedding)

        if is_match:
            print(f"✅ Identity VERIFIED for student {student.id}")
            return {"message": "Identity verified! You may begin the exam.", "match": True}
        else:
            print(f"❌ Identity MISMATCH for student {student.id}")
            raise HTTPException(status_code=403, detail="Face does not match the registered student. Access Denied.")
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="No face detected in live feed. Please face the camera.")
    except Exception as e:
        print(f"❌ Verification error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/student/exams/{exam_id}/continuous-verify")
def continuous_identity_check(
    exam_id: int,
    request: ContinuousVerifyRequest,
    student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """
    Continuous identity verification during exam.
    Called every 15 seconds from frontend with webcam screenshot.

    Returns:
        match: True if same person or skipped
        skipped: True if no face detected (temporary failure)
        message: Human-readable status
    """
    from services.face_service import process_and_extract_embedding, compare_faces

    if not student.face_embedding:
        print(f"❌ No registered face for student {student.id}")
        raise HTTPException(status_code=400, detail="No registered face found")

    try:
        print(f"🔍 Continuous identity check for student {student.id}")
        # Use enforce_detection=False for continuous checks
        live_embedding = process_and_extract_embedding(request.image_base64, enforce_detection=False)

        # No face detected in this frame — skip verification, don't penalize
        if live_embedding is None:
            print(f"⚠️ No clear face in frame for student {student.id}")
            return {
                "match": True,  # Don't penalize for temporary detection failures
                "skipped": True,
                "message": "No clear face detected in frame - please face the camera",
            }

        # Compare embeddings
        is_match = compare_faces(student.face_embedding, live_embedding)
        result = "✅ MATCH" if is_match else "❌ MISMATCH"
        print(f"{result} - Identity verification for student {student.id}")

        return {
            "match": is_match,
            "skipped": False,
            "message": "Identity verified" if is_match else "Identity mismatch detected",
        }
    except Exception as e:
        print(f"❌ Continuous verification error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Routes: Photo Upload ─────────────────────────────────────────────────────

@router.post("/student/photo/upload")
async def upload_face_photo(
    file: UploadFile = File(...),
    student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """Upload a face photo for the student. Saves to uploads/photos/{student_id}.jpg."""
    if file.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, or WebP images are allowed")

    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 5MB allowed.")

    photos_dir = os.path.join(UPLOAD_DIR, "photos")
    os.makedirs(photos_dir, exist_ok=True)

    ext = "jpg" if "jpeg" in file.content_type else file.content_type.split("/")[-1]
    filename = f"{student.id}.{ext}"
    filepath = os.path.join(photos_dir, filename)

    with open(filepath, "wb") as f:
        f.write(contents)

    relative_path = f"photos/{filename}"
    student.face_photo_url = relative_path
    db.commit()

    return {"message": "Photo uploaded successfully", "photo_url": f"/uploads/{relative_path}"}


@router.get("/student/photo")
def get_face_photo(student: Student = Depends(get_current_student)):
    """Get the current student's face photo URL."""
    if not student.face_photo_url:
        return {"photo_url": None, "has_photo": False}
    return {"photo_url": f"/uploads/{student.face_photo_url}", "has_photo": True}


# ─── Routes: Proctoring Events ────────────────────────────────────────────────

@router.post("/student/exams/{exam_id}/proctoring-event")
def log_proctoring_event(
    exam_id: int,
    request: ProctoringEventRequest,
    student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """Log a proctoring event during an exam. Optionally saves a snapshot."""
    instance = (
        db.query(McqStudentExamInstance)
        .filter(
            McqStudentExamInstance.exam_id == exam_id,
            McqStudentExamInstance.student_id == student.id,
        )
        .first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="No active exam instance found")

    # Save snapshot if provided
    snapshot_path = None
    if request.snapshot_base64:
        snapshot_path = _save_snapshot(request.snapshot_base64, instance.id)

    # Create proctoring event
    event = ProctoringEvent(
        instance_id=instance.id,
        student_id=student.id,
        event_type=request.event_type,
        details=request.details,
        snapshot_url=f"snapshots/{instance.id}/{os.path.basename(snapshot_path)}" if snapshot_path else None,
    )
    db.add(event)
    db.commit()

    return {"status": "Event logged", "event_type": request.event_type}


@router.get("/student/exams/{exam_id}/proctoring-events")
def get_proctoring_events(
    exam_id: int,
    student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """Get proctoring events for the student's exam instance."""
    instance = (
        db.query(McqStudentExamInstance)
        .filter(
            McqStudentExamInstance.exam_id == exam_id,
            McqStudentExamInstance.student_id == student.id,
        )
        .first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="No exam instance found")

    events = (
        db.query(ProctoringEvent)
        .filter(ProctoringEvent.instance_id == instance.id)
        .order_by(ProctoringEvent.created_at.asc())
        .all()
    )

    return [
        {
            "id": e.id,
            "event_type": e.event_type,
            "details": e.details,
            "snapshot_url": f"/uploads/{e.snapshot_url}" if e.snapshot_url else None,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]
