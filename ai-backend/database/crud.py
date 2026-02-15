"""
CRUD operations for structure truth layer
All database operations go through these functions
"""

from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from database import models, schemas


# ==========================================
# SUBJECT CRUD
# ==========================================

def create_subject(db: Session, subject: schemas.SubjectCreate) -> models.Subject:
    """Create a new subject"""
    db_subject = models.Subject(
        name=subject.name,
        description=subject.description
    )
    db.add(db_subject)
    db.commit()
    db.refresh(db_subject)
    return db_subject


def get_subject(db: Session, subject_id: int) -> Optional[models.Subject]:
    """Get subject by ID"""
    return db.query(models.Subject).filter(models.Subject.id == subject_id).first()


def get_subject_by_name(db: Session, name: str) -> Optional[models.Subject]:
    """Get subject by name"""
    return db.query(models.Subject).filter(models.Subject.name == name).first()


def get_subjects(db: Session, skip: int = 0, limit: int = 100) -> List[models.Subject]:
    """Get all subjects with pagination"""
    return db.query(models.Subject).offset(skip).limit(limit).all()


def get_subject_with_units(db: Session, subject_id: int) -> Optional[models.Subject]:
    """Get subject with all its units loaded"""
    return db.query(models.Subject).options(
        joinedload(models.Subject.units)
    ).filter(models.Subject.id == subject_id).first()


def get_subject_complete(db: Session, subject_id: int) -> Optional[models.Subject]:
    """Get subject with full hierarchy (units + concepts)"""
    return db.query(models.Subject).options(
        joinedload(models.Subject.units).joinedload(models.Unit.concepts)
    ).filter(models.Subject.id == subject_id).first()


def update_subject(db: Session, subject_id: int, subject_update: schemas.SubjectUpdate) -> Optional[models.Subject]:
    """Update an existing subject"""
    db_subject = get_subject(db, subject_id)
    if not db_subject:
        return None
    
    update_data = subject_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_subject, field, value)
    
    db.commit()
    db.refresh(db_subject)
    return db_subject


def delete_subject(db: Session, subject_id: int) -> bool:
    """Delete a subject (cascades to units and concepts)"""
    db_subject = get_subject(db, subject_id)
    if not db_subject:
        return False
    
    db.delete(db_subject)
    db.commit()
    return True


# ==========================================
# UNIT CRUD
# ==========================================

def create_unit(db: Session, unit: schemas.UnitCreate) -> models.Unit:
    """Create a new unit"""
    db_unit = models.Unit(
        name=unit.name,
        description=unit.description,
        order=unit.order,
        subject_id=unit.subject_id
    )
    db.add(db_unit)
    db.commit()
    db.refresh(db_unit)
    return db_unit


def get_unit(db: Session, unit_id: int) -> Optional[models.Unit]:
    """Get unit by ID"""
    return db.query(models.Unit).filter(models.Unit.id == unit_id).first()


def get_units_by_subject(db: Session, subject_id: int) -> List[models.Unit]:
    """Get all units for a subject, ordered by order field"""
    return db.query(models.Unit).filter(
        models.Unit.subject_id == subject_id
    ).order_by(models.Unit.order).all()


def get_unit_with_concepts(db: Session, unit_id: int) -> Optional[models.Unit]:
    """Get unit with all its concepts loaded"""
    return db.query(models.Unit).options(
        joinedload(models.Unit.concepts)
    ).filter(models.Unit.id == unit_id).first()


def update_unit(db: Session, unit_id: int, unit_update: schemas.UnitUpdate) -> Optional[models.Unit]:
    """Update an existing unit"""
    db_unit = get_unit(db, unit_id)
    if not db_unit:
        return None
    
    update_data = unit_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_unit, field, value)
    
    db.commit()
    db.refresh(db_unit)
    return db_unit


def delete_unit(db: Session, unit_id: int) -> bool:
    """Delete a unit (cascades to concepts)"""
    db_unit = get_unit(db, unit_id)
    if not db_unit:
        return False
    
    db.delete(db_unit)
    db.commit()
    return True


# ==========================================
# CONCEPT CRUD
# ==========================================

def create_concept(db: Session, concept: schemas.ConceptCreate) -> models.Concept:
    """Create a new concept"""
    db_concept = models.Concept(
        name=concept.name,
        description=concept.description,
        diagram_critical=concept.diagram_critical,
        order=concept.order,
        unit_id=concept.unit_id
    )
    db.add(db_concept)
    db.commit()
    db.refresh(db_concept)
    return db_concept


def get_concept(db: Session, concept_id: int) -> Optional[models.Concept]:
    """Get concept by ID"""
    return db.query(models.Concept).filter(models.Concept.id == concept_id).first()


def get_concepts_by_unit(db: Session, unit_id: int) -> List[models.Concept]:
    """Get all concepts for a unit, ordered by order field"""
    return db.query(models.Concept).filter(
        models.Concept.unit_id == unit_id
    ).order_by(models.Concept.order).all()


def get_diagram_critical_concepts(db: Session, subject_id: Optional[int] = None) -> List[models.Concept]:
    """Get all diagram-critical concepts, optionally filtered by subject"""
    query = db.query(models.Concept).filter(models.Concept.diagram_critical == True)
    
    if subject_id:
        query = query.join(models.Unit).filter(models.Unit.subject_id == subject_id)
    
    return query.all()


def update_concept(db: Session, concept_id: int, concept_update: schemas.ConceptUpdate) -> Optional[models.Concept]:
    """Update an existing concept"""
    db_concept = get_concept(db, concept_id)
    if not db_concept:
        return None
    
    update_data = concept_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_concept, field, value)
    
    db.commit()
    db.refresh(db_concept)
    return db_concept


def delete_concept(db: Session, concept_id: int) -> bool:
    """Delete a concept"""
    db_concept = get_concept(db, concept_id)
    if not db_concept:
        return False
    
    db.delete(db_concept)
    db.commit()
    return True


# ==========================================
# BULK OPERATIONS
# ==========================================

def bulk_create_units(db: Session, subject_id: int, units: List[schemas.UnitCreate]) -> List[models.Unit]:
    """Create multiple units at once for a subject"""
    db_units = [
        models.Unit(
            name=unit.name,
            description=unit.description,
            order=unit.order,
            subject_id=subject_id
        )
        for unit in units
    ]
    db.add_all(db_units)
    db.commit()
    for unit in db_units:
        db.refresh(unit)
    return db_units


def bulk_create_concepts(db: Session, unit_id: int, concepts: List[schemas.ConceptCreate]) -> List[models.Concept]:
    """Create multiple concepts at once for a unit"""
    db_concepts = [
        models.Concept(
            name=concept.name,
            description=concept.description,
            diagram_critical=concept.diagram_critical,
            order=concept.order,
            unit_id=unit_id
        )
        for concept in concepts
    ]
    db.add_all(db_concepts)
    db.commit()
    for concept in db_concepts:
        db.refresh(concept)
    return db_concepts
