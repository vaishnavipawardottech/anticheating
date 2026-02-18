"""
Structure Truth Layer API
FastAPI application for managing academic structure: Subject → Unit → Concept

This is the SOURCE OF TRUTH for academic structure.
NO document processing, NO embeddings, NO LLM usage here.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from database.database import engine, Base
from routers import subjects, units, concepts, structure_ai, documents, cleanup, alignment, documents_db, search, context, exams, questions


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and shutdown events
    Creates database tables on startup
    """
    # Create all tables
    Base.metadata.create_all(bind=engine)
    yield
    # Cleanup on shutdown (if needed)


# Create FastAPI app
app = FastAPI(
    title="Academic Structure API",
    description="Structure Truth Layer - Subject → Unit → Concept hierarchy management",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers (documents_db before documents so GET /documents/elements-with-embeddings
# is matched before GET /documents/{document_id}, avoiding 422)
app.include_router(subjects.router)
app.include_router(units.router)
app.include_router(concepts.router)
app.include_router(structure_ai.router)
app.include_router(documents_db.router)
app.include_router(documents.router)
app.include_router(cleanup.router)
app.include_router(alignment.router)
app.include_router(search.router)  # Semantic search endpoint
app.include_router(context.router)  # Context builder for RAG
app.include_router(exams.router)   # Exam generation
app.include_router(questions.router)  # Layer 3: Question bank (concept-centric pipeline)


@app.get("/")
def root():
    """
    Root endpoint - API info
    """
    return {
        "name": "Academic Structure API",
        "version": "1.0.0",
        "description": "Structure Truth Layer for academic ingestion system",
        "structure": "Subject → Unit → Concept",
        "endpoints": {
            "subjects": "/subjects",
            "units": "/units",
            "concepts": "/concepts",
            "structure_ai": "/structure",
            "documents": "/documents",
            "search": "/search",
            "docs": "/docs"
        }
    }


@app.get("/health")
def health_check():
    """
    Health check endpoint
    """
    return {
        "status": "healthy",
        "service": "structure-api",
        "database": "connected"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
