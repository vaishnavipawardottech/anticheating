"""
Subject API endpoints
CRUD operations for subjects (top-level structure)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from database import schemas, crud
from database.database import get_db
from database.models import Document
from embeddings.qdrant_manager import get_qdrant_manager

router = APIRouter(prefix="/subjects", tags=["subjects"])


@router.post("/", response_model=schemas.SubjectResponse, status_code=status.HTTP_201_CREATED)
def create_subject(subject: schemas.SubjectCreate, db: Session = Depends(get_db)):
    """
    Create a new subject
    Subject names must be unique
    """
    # Check if subject with same name exists
    existing = crud.get_subject_by_name(db, subject.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Subject with name '{subject.name}' already exists"
        )
    
    return crud.create_subject(db, subject)


@router.get("/", response_model=List[schemas.SubjectResponse])
def list_subjects(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    List all subjects with pagination
    """
    return crud.get_subjects(db, skip=skip, limit=limit)


@router.get("/with-stats/all")
def list_subjects_with_stats(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    List all subjects with document counts and unit/concept statistics
    """
    from database.models import Document, Unit, Concept
    from sqlalchemy import func
    
    subjects = crud.get_subjects(db, skip=skip, limit=limit)
    
    result = []
    for subject in subjects:
        # Count documents
        doc_count = db.query(func.count(Document.id)).filter(Document.subject_id == subject.id).scalar()
        
        # Count units
        unit_count = db.query(func.count(Unit.id)).filter(Unit.subject_id == subject.id).scalar()
        
        # Count concepts
        concept_count = db.query(func.count(Concept.id)).join(Unit).filter(Unit.subject_id == subject.id).scalar()
        
        result.append({
            "id": subject.id,
            "name": subject.name,
            "description": subject.description,
            "created_at": subject.created_at,
            "document_count": doc_count or 0,
            "unit_count": unit_count or 0,
            "concept_count": concept_count or 0
        })
    
    return result


@router.get("/{subject_id}", response_model=schemas.SubjectResponse)
def get_subject(subject_id: int, db: Session = Depends(get_db)):
    """
    Get a specific subject by ID
    """
    subject = crud.get_subject(db, subject_id)
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subject with ID {subject_id} not found"
        )
    return subject


@router.get("/{subject_id}/with-units", response_model=schemas.SubjectWithUnits)
def get_subject_with_units(subject_id: int, db: Session = Depends(get_db)):
    """
    Get a subject with all its units (no concepts)
    """
    subject = crud.get_subject_with_units(db, subject_id)
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subject with ID {subject_id} not found"
        )
    return subject


@router.get("/{subject_id}/complete", response_model=schemas.SubjectComplete)
def get_subject_complete(subject_id: int, db: Session = Depends(get_db)):
    """
    Get complete subject hierarchy: subject → units → concepts
    """
    subject = crud.get_subject_complete(db, subject_id)
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subject with ID {subject_id} not found"
        )
    return subject


@router.put("/{subject_id}", response_model=schemas.SubjectResponse)
def update_subject(
    subject_id: int,
    subject_update: schemas.SubjectUpdate,
    db: Session = Depends(get_db)
):
    """
    Update a subject
    Only provided fields will be updated
    """
    subject = crud.update_subject(db, subject_id, subject_update)
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subject with ID {subject_id} not found"
        )
    return subject


@router.get("/{subject_id}/with-documents")
def get_subject_with_documents(subject_id: int, db: Session = Depends(get_db)):
    """
    Get a subject with all its documents
    Returns subject info, structure (units, concepts), and uploaded documents
    """
    from database.models import Document
    
    subject = crud.get_subject_complete(db, subject_id)
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subject with ID {subject_id} not found"
        )
    
    # Get all documents for this subject
    documents = db.query(Document).filter(Document.subject_id == subject_id).all()
    
    return {
        "id": subject.id,
        "name": subject.name,
        "description": subject.description,
        "created_at": subject.created_at,
        "math_mode": getattr(subject, "math_mode", False),
        "formula_mode": getattr(subject, "formula_mode", False),
        "vision_budget": getattr(subject, "vision_budget", None),
        "units": [
            {
                "id": unit.id,
                "name": unit.name,
                "description": unit.description,
                "order": unit.order,
                "concepts": [
                    {
                        "id": concept.id,
                        "name": concept.name,
                        "description": concept.description,
                        "diagram_critical": concept.diagram_critical,
                        "order": concept.order
                    }
                    for concept in unit.concepts
                ]
            }
            for unit in subject.units
        ],
        "documents": [
            {
                "id": doc.id,
                "filename": doc.filename,
                "file_type": doc.file_type,
                "file_size_bytes": doc.file_size_bytes,
                "status": doc.status,
                "upload_timestamp": doc.upload_timestamp,
                "indexed_at": doc.indexed_at
            }
            for doc in documents
        ],
        "document_count": len(documents)
    }


@router.delete("/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subject(subject_id: int, db: Session = Depends(get_db)):
    """
    Delete a subject and all related data (units, concepts, documents, exams).
    Also removes document vectors from Qdrant.
    """
    if not crud.get_subject(db, subject_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subject with ID {subject_id} not found"
        )
    # Get doc IDs without loading Document entities (avoids StaleDataError on delete)
    doc_ids = [r[0] for r in db.query(Document.id).filter(Document.subject_id == subject_id).all()]
    try:
        qdrant = get_qdrant_manager()
        for did in doc_ids:
            qdrant.delete_by_document(did)
    except Exception as e:
        print(f"⚠ Qdrant cleanup during subject delete: {e}")
    success = crud.delete_subject(db, subject_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subject with ID {subject_id} not found"
        )
    return None
