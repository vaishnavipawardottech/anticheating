"""
Subject API endpoints
CRUD operations for subjects (top-level structure)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from database import schemas, crud
from database.database import get_db

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


@router.delete("/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subject(subject_id: int, db: Session = Depends(get_db)):
    """
    Delete a subject
    WARNING: This will cascade delete all units and concepts
    """
    success = crud.delete_subject(db, subject_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subject with ID {subject_id} not found"
        )
    return None
