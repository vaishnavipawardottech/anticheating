from database import SessionLocal
from models.exam_log import ExamLog
from services.queue import huey_queue

# This decorator turns the function into a background task!
@huey_queue.task()
def save_event_to_db(student_id: int, event_type: str, details: str = ""):
    """Executed by the Huey Background Worker, NOT FastAPI!"""
    db = SessionLocal()
    try:
        new_log = ExamLog(
            student_id=student_id, 
            event_type=event_type, 
            details=details
        )
        db.add(new_log)
        db.commit()
    except Exception as e:
        print(f"Error saving event to database: {e}")
    finally:
        db.close()