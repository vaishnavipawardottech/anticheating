import base64
import os

from database import SessionLocal
from models.exam_log import ExamLog
from services.queue import huey_queue

def _save_snapshot(snapshot_base64: str, student_id: int) -> str:
    """Save snapshot to snapshots/{student_id}/{timestamp}.jpg"""
    if not snapshot_base64:
        return None
    
    try:
        if "," in snapshot_base64:
            snapshot_base64 = snapshot_base64.split(",", 1)[1]

        backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        student_snapshots_dir = os.path.join(backend_root, "snapshots", str(student_id))
        os.makedirs(student_snapshots_dir, exist_ok=True)

        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        filename = f"{timestamp}.jpg"
        relative_path = os.path.join("snapshots", str(student_id), filename)
        absolute_path = os.path.join(backend_root, relative_path)

        decoded_data = base64.b64decode(snapshot_base64)
        with open(absolute_path, "wb") as snapshot_file:
            snapshot_file.write(decoded_data)

        print(f"✅ Snapshot saved: {relative_path}")
        return relative_path
    except Exception as e:
        print(f"❌ Error saving snapshot: {e}")
        return None

# This decorator turns the function into a background task!
@huey_queue.task()
def save_event_to_db(
    student_id: int,
    event_type: str,
    details: str = "",
    snapshot_base64: str | None = None,
    email: str | None = None,
):
    """Executed by the Huey Background Worker, NOT FastAPI!"""
    db = SessionLocal()
    try:
        snapshot_path = None
        if snapshot_base64 and snapshot_base64.strip():
            snapshot_path = _save_snapshot(snapshot_base64, student_id)
        
        # Append snapshot path to details if available
        final_details = details
        if snapshot_path:
            if final_details:
                final_details = f"{final_details} | snapshot_path={snapshot_path}"
            else:
                final_details = f"snapshot_path={snapshot_path}"

        new_log = ExamLog(
            student_id=student_id, 
            event_type=event_type, 
            details=final_details
        )
        db.add(new_log)
        db.commit()
        print(f"✅ Event logged: {event_type} for student {student_id}")
    except Exception as e:
        print(f"❌ Error saving event to database: {e}")
        db.rollback()
    finally:
        db.close()