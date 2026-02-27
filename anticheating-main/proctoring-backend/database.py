from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# The PostgreSQL Connection String Format:
# postgresql://<username>:<password>@<host>:<port>/<database_name>
# Change 'postgres', 'yourpassword', and 'proctoring_db' to match your local setup
SQLALCHEMY_DATABASE_URL = "postgresql://postgres:postgres@localhost:5433/proctoring_db"

# We removed the SQLite-specific connect_args
engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()