"""
Concept API endpoints
CRUD operations for concepts (atomic knowledge units under units)
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from database import schemas, crud
from database.database import get_db

router = APIRouter(prefix="/concepts", tags=["concepts"])


@router.post("/", response_model=schemas.ConceptResponse, status_code=status.HTTP_201_CREATED)
def create_concept(concept: schemas.ConceptCreate, db: Session = Depends(get_db)):
    """
    Create a new concept under a unit
    """
    # Verify unit exists
    unit = crud.get_unit(db, concept.unit_id)
    if not unit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unit with ID {concept.unit_id} not found"
        )
    
    return crud.create_concept(db, concept)


@router.get("/unit/{unit_id}", response_model=List[schemas.ConceptResponse])
def list_concepts_by_unit(unit_id: int, db: Session = Depends(get_db)):
    """
    List all concepts for a unit, ordered by order field
    """
    # Verify unit exists
    unit = crud.get_unit(db, unit_id)
    if not unit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unit with ID {unit_id} not found"
        )
    
    return crud.get_concepts_by_unit(db, unit_id)


@router.get("/diagram-critical", response_model=List[schemas.ConceptResponse])
def list_diagram_critical_concepts(
    subject_id: Optional[int] = Query(None, description="Filter by subject ID"),
    db: Session = Depends(get_db)
):
    """
    List all diagram-critical concepts
    Optionally filter by subject
    """
    if subject_id:
        # Verify subject exists
        subject = crud.get_subject(db, subject_id)
        if not subject:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Subject with ID {subject_id} not found"
            )
    
    return crud.get_diagram_critical_concepts(db, subject_id)


@router.get("/{concept_id}", response_model=schemas.ConceptResponse)
def get_concept(concept_id: int, db: Session = Depends(get_db)):
    """
    Get a specific concept by ID
    """
    concept = crud.get_concept(db, concept_id)
    if not concept:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Concept with ID {concept_id} not found"
        )
    return concept


@router.put("/{concept_id}", response_model=schemas.ConceptResponse)
def update_concept(
    concept_id: int,
    concept_update: schemas.ConceptUpdate,
    db: Session = Depends(get_db)
):
    """
    Update a concept
    Only provided fields will be updated
    """
    concept = crud.update_concept(db, concept_id, concept_update)
    if not concept:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Concept with ID {concept_id} not found"
        )
    return concept


@router.delete("/{concept_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_concept(concept_id: int, db: Session = Depends(get_db)):
    """
    Delete a concept
    """
    success = crud.delete_concept(db, concept_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Concept with ID {concept_id} not found"
        )
    return None
