"""Check existing subjects, units, concepts, and documents"""
from database.database import SessionLocal
from database.models import Subject, Unit, Concept, Document

db = SessionLocal()

# Check subjects
subjects = db.query(Subject).all()
print('📚 SUBJECTS:', len(subjects))
for s in subjects:
    print(f'  - {s.id}: {s.name}')

# Check units
units = db.query(Unit).all()
print('\n📖 UNITS:', len(units))
for u in units:
    print(f'  - {u.id}: {u.name} (subject_id={u.subject_id})')

# Check concepts
concepts = db.query(Concept).all()
print('\n🎯 CONCEPTS:', len(concepts))
for c in concepts:
    print(f'  - {c.id}: {c.name} (unit_id={c.unit_id})')

# Check documents
docs = db.query(Document).all()
print('\n📄 DOCUMENTS:', len(docs))
for d in docs:
    print(f'  - {d.id}: {d.filename} (subject_id={d.subject_id}, status={d.status})')

db.close()
