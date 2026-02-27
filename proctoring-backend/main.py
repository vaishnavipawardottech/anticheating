import os
# Turns off the oneDNN warning
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
# Forces TensorFlow to only print critical errors, hiding all INFO logs
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base

# --- NEW IMPORTS: Crucial for creating the tables in PostgreSQL ---
from models.student import Student
from models.exam_log import ExamLog

from routers import auth
from routers import exam

# Create the database tables on startup (It now sees Student and ExamLog!)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Proctoring Backend Engine")

# Crucial for React to talk to FastAPI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Change to ["http://localhost:5173"] in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Attach the endpoints
app.include_router(auth.router)
app.include_router(exam.router)

@app.get("/")
def read_root():
    return {"status": "Online"}