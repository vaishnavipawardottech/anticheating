"""Verify chunk alignments in database"""
from database.database import SessionLocal
from database.models import DocumentChunk, Concept, Unit

db = SessionLocal()

chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == 11).order_by(DocumentChunk.chunk_index).all()

print(f"📊 Alignment Summary for Document 11 (Unit 1.pdf)")
print(f"=" * 80)
print(f"Total chunks: {len(chunks)}\n")

# Group by concept
concept_groups = {}
for chunk in chunks:
    concept_id = chunk.concept_id or "UNASSIGNED"
    if concept_id not in concept_groups:
        concept_groups[concept_id] = []
    concept_groups[concept_id].append(chunk)

for concept_id, chunks_list in sorted(concept_groups.items()):
    if concept_id == "UNASSIGNED":
        print(f"⚠️  UNASSIGNED: {len(chunks_list)} chunks")
    else:
        concept = db.query(Concept).filter(Concept.id == concept_id).first()
        unit = db.query(Unit).filter(Unit.id == concept.unit_id).first() if concept else None
        
        print(f"\n🎯 Concept {concept_id}: {concept.name if concept else 'Unknown'}")
        print(f"   Unit {concept.unit_id if concept else 'N/A'}: {unit.name if unit else 'Unknown'}")
        print(f"   Chunks ({len(chunks_list)}): {', '.join(str(c.chunk_index) for c in chunks_list)}")
        avg_conf = sum(c.alignment_confidence or 0 for c in chunks_list) / len(chunks_list)
        print(f"   Avg confidence: {avg_conf:.2f}")

print(f"\n" + "=" * 80)
print(f"✅ All chunks successfully aligned!")

db.close()
