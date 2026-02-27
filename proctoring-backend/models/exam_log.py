from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from database import Base

from models.student import Student

class ExamLog(Base):
    __tablename__ = "exam_logs"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id"), index=True)
    
    event_type = Column(String, index=True) # e.g., "TAB_SWITCH", "FULLSCREEN_EXIT"
    details = Column(String, nullable=True) # e.g., "Student opened a new tab"
    
    timestamp = Column(DateTime(timezone=True), server_default=func.now())