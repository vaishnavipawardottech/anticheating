from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from database import Base

class Student(Base):
    __tablename__ = "students"

    # ID is now the only identifier and auto-increments automatically
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    refresh_token = Column(String, nullable=True)
    
    # Automatically saves the exact timestamp when registered
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    embedding = Column(JSONB, nullable=True)

    def set_embedding(self, embedding_list):
        self.embedding = embedding_list 

    def get_embedding(self):
        return self.embedding