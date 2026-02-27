from fastapi import APIRouter, Depends
from pydantic import BaseModel
from services.auth import get_current_user_id
from services.tasks import save_event_to_db

router = APIRouter(prefix="/api/exam", tags=["Exam"])

class EventRequest(BaseModel):
    event_type: str
    details: str = ""

@router.post("/log-event")
def log_student_event(
    request: EventRequest, 
    student_id: int = Depends(get_current_user_id)
):
    # Because of the @huey_queue.task() decorator, this doesn't run the function.
    # Instead, it instantly packages it and sends it to Valkey!
    save_event_to_db(student_id, request.event_type, request.details)
    
    return {"status": "Event queued to Valkey successfully"}