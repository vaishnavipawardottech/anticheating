"""Align document chunks to concepts using AI"""
import asyncio
import sys
from database.database import SessionLocal
from database.models import Document, DocumentChunk
from routers.alignment import align_document, AlignDocumentRequest

async def main():
    db = SessionLocal()
    
    # Check document
    doc = db.query(Document).filter(Document.id == 11).first()
    if not doc:
        print("❌ Document 11 not found")
        return
    
    print(f"📄 Document: {doc.filename}")
    print(f"📚 Subject: {doc.subject_id}")
    
    # Check chunks before alignment
    chunks_before = db.query(DocumentChunk).filter(DocumentChunk.document_id == 11).all()
    print(f"\n🔍 Found {len(chunks_before)} chunks")
    
    aligned_before = sum(1 for c in chunks_before if c.concept_id is not None)
    print(f"   Aligned before: {aligned_before}/{len(chunks_before)}")
    
    # Get chunk IDs for alignment
    chunk_ids = [c.id for c in chunks_before]
    print(f"\n🎯 Aligning {len(chunk_ids)} chunks to concepts...")
    
    # Run alignment using chunk_ids (not document_id)
    # This aligns DocumentChunks, not ParsedElements
    request = AlignDocumentRequest(chunk_ids=chunk_ids)
    
    try:
        result = await align_document(request, db)
        
        print(f"\n✅ Alignment complete!")
        print(f"   Total chunks: {result.total_elements}")
        print(f"   Aligned: {result.aligned}")
        print(f"   Unassigned: {result.unassigned}")
        print(f"   Success rate: {result.aligned / result.total_elements * 100:.1f}%")
        
        # Check chunks after alignment
        chunks_after = db.query(DocumentChunk).filter(DocumentChunk.document_id == 11).all()
        
        print(f"\n📊 Chunk assignments:")
        for chunk in chunks_after:
            if chunk.concept_id:
                print(f"   Chunk {chunk.chunk_index}: concept_id={chunk.concept_id}, "
                      f"unit_id={chunk.unit_id}, confidence={chunk.alignment_confidence:.2f}")
            else:
                print(f"   Chunk {chunk.chunk_index}: UNASSIGNED")
        
    except Exception as e:
        print(f"❌ Alignment failed: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(main())
