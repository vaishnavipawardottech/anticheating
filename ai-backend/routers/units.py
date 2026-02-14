"""
Unit API endpoints
CRUD operations for units (mid-level structure under subjects)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from database import schemas, crud
from database.database import get_db

router = APIRouter(prefix="/units", tags=["units"])


@router.post("/", response_model=schemas.UnitResponse, status_code=status.HTTP_201_CREATED)
def create_unit(unit: schemas.UnitCreate, db: Session = Depends(get_db)):
    """
    Create a new unit under a subject
    """
    # Verify subject exists
    subject = crud.get_subject(db, unit.subject_id)
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subject with ID {unit.subject_id} not found"
        )
    
    return crud.create_unit(db, unit)


@router.get("/subject/{subject_id}", response_model=List[schemas.UnitResponse])
def list_units_by_subject(subject_id: int, db: Session = Depends(get_db)):
    """
    List all units for a subject, ordered by order field
    """
    # Verify subject exists
    subject = crud.get_subject(db, subject_id)
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subject with ID {subject_id} not found"
        )
    
    return crud.get_units_by_subject(db, subject_id)


@router.get("/{unit_id}", response_model=schemas.UnitResponse)
def get_unit(unit_id: int, db: Session = Depends(get_db)):
    """
    Get a specific unit by ID
    """
    unit = crud.get_unit(db, unit_id)
    if not unit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unit with ID {unit_id} not found"
        )
    return unit


@router.get("/{unit_id}/with-concepts", response_model=schemas.UnitWithConcepts)
def get_unit_with_concepts(unit_id: int, db: Session = Depends(get_db)):
    """
    Get a unit with all its concepts
    """
    unit = crud.get_unit_with_concepts(db, unit_id)
    if not unit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unit with ID {unit_id} not found"
        )
    return unit


@router.put("/{unit_id}", response_model=schemas.UnitResponse)
def update_unit(
    unit_id: int,
    unit_update: schemas.UnitUpdate,
    db: Session = Depends(get_db)
):
    """
    Update a unit
    Only provided fields will be updated
    """
    unit = crud.update_unit(db, unit_id, unit_update)
    if not unit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unit with ID {unit_id} not found"
        )
    return unit


@router.delete("/{unit_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_unit(unit_id: int, db: Session = Depends(get_db)):
    """
    Delete a unit
    WARNING: This will cascade delete all concepts
    """
    success = crud.delete_unit(db, unit_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unit with ID {unit_id} not found"
        )
    return None
