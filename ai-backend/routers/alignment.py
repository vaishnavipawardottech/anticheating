"""
Alignment Router
Maps cleaned document elements to concepts using Gemini API
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional
import json

from database.database import get_db
from database.models import Concept, Unit, AlignedElement, ParsedElement, DocumentChunk, Document
from parsing.schemas import SemanticElement
from routers.structure_ai import call_gemini_flash
from embeddings.qdrant_manager import get_qdrant_manager
from qdrant_client.models import PointStruct

router = APIRouter(prefix="/alignment", tags=["alignment"])


# Schemas
class AlignmentRequest(BaseModel):
    """Request to align elements to concepts"""
    subject_id: int = Field(..., description="Subject ID to get concepts from")
    elements: List[SemanticElement] = Field(..., description="Cleaned elements to align")


class AlignmentResult(BaseModel):
    """Single element alignment result"""
    element_order: int
    concept_id: Optional[int]
    status: str  # ALIGNED, UNASSIGNED
    confidence: Optional[float]


class AlignmentResponse(BaseModel):
    """Response with alignment statistics"""
    total_elements: int
    aligned: int
    unassigned: int
    results: List[AlignmentResult]


# Prompt template
ALIGNMENT_PROMPT = """You are classifying document elements to academic concepts.

AVAILABLE CONCEPTS:
{concepts_list}

ELEMENTS TO CLASSIFY:
{elements_json}

TASK: For each element, determine which concept (by ID) it belongs to.

RULES:
- Return concept_id from the concepts list above, or null if no good match
- Include confidence score between 0.0 and 1.0
- If confidence < 0.7, use null for concept_id
- Match based on semantic meaning, not just keywords

CRITICAL: You MUST return a valid JSON array with this exact structure:
[
  {{"order": 0, "concept_id": 2, "confidence": 0.95}},
  {{"order": 1, "concept_id": null, "confidence": 0.45}}
]

Return ONLY the JSON array. No explanations. No markdown. Just the array."""


def chunk_list(lst: List, size: int):
    """Split list into chunks of given size"""
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


async def align_batch(elements: List[SemanticElement], concepts: List[Concept]) -> List[dict]:
    """
    Align a batch of elements using Gemini
    
    Returns list of {order, concept_id, confidence}
    """
    # Build concepts list
    concepts_list = "\n".join([
        f"{c.id}. {c.name}" for c in concepts
    ])
    
    # Build elements JSON
    elements_data = [
        {"order": e.order, "text": e.text or f"[{e.element_type}]"}
        for e in elements
    ]
    elements_json = json.dumps(elements_data, indent=2)
    
    # Build prompt
    prompt = ALIGNMENT_PROMPT.format(
        concepts_list=concepts_list,
        elements_json=elements_json
    )
    
    # Call Gemini
    response = await call_gemini_flash(prompt)
    
    # Parse JSON
    try:
        # Extract JSON from response
        text = response.strip()
        
        # Log the response for debugging
        print(f"📄 Gemini response preview: {text[:200]}...")
        
        start_idx = text.find("[")
        end_idx = text.rfind("]") + 1
        
        if start_idx == -1 or end_idx == 0:
            print(f"❌ No JSON array found. Full response: {text}")
            raise ValueError("No JSON array found in response")
        
        json_str = text[start_idx:end_idx]
        results = json.loads(json_str)
        
        print(f"✅ Parsed {len(results)} alignment results")
        return results
    except Exception as e:
        print(f"❌ Parse error: {str(e)}")
        print(f"❌ Full response was: {response}")
        raise HTTPException(status_code=500, detail=f"Failed to parse Gemini response: {str(e)}")


@router.post("/align", response_model=AlignmentResponse)
async def align_elements(request: AlignmentRequest, db: Session = Depends(get_db)):
    """
    Align document elements to concepts
    
    Uses Gemini API to classify each element
    Processes in batches of 10 for efficiency
    """
    # 1. Load concepts for this subject
    concepts = db.query(Concept).join(Unit).filter(
        Unit.subject_id == request.subject_id
    ).all()
    
    if not concepts:
        raise HTTPException(status_code=404, detail=f"No concepts found for subject_id={request.subject_id}")
    
    print(f"🎯 Aligning {len(request.elements)} elements to {len(concepts)} concepts")
    
    # 2. Process in batches
    all_results = []
    batch_size = 10
    
    try:
        for batch_idx, batch in enumerate(chunk_list(request.elements, batch_size)):
            print(f"📦 Processing batch {batch_idx + 1} ({len(batch)} elements)...")
            try:
                batch_results = await align_batch(batch, concepts)
                all_results.extend(batch_results)
                print(f"✅ Batch {batch_idx + 1} completed")
            except Exception as batch_error:
                print(f"❌ Batch {batch_idx + 1} failed: {str(batch_error)}")
                # Continue with next batch instead of failing completely
                # Add UNASSIGNED results for failed batch
                for elem in batch:
                    all_results.append({
                        "order": elem.order,
                        "concept_id": None,
                        "confidence": 0.0
                    })
    except Exception as e:
        print(f"❌ Fatal error during alignment: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Alignment failed: {str(e)}")
    
    # 3. Build response
    aligned_count = 0
    unassigned_count = 0
    results = []
    
    for result in all_results:
        concept_id = result.get("concept_id")
        confidence = result.get("confidence", 0.0)
        
        if concept_id is not None:
            status = "ALIGNED"
            aligned_count += 1
        else:
            status = "UNASSIGNED"
            unassigned_count += 1
        
        results.append(AlignmentResult(
            element_order=result["order"],
            concept_id=concept_id,
            status=status,
            confidence=confidence
        ))
    
    print(f"✅ Aligned: {aligned_count}, ⚠️ Unassigned: {unassigned_count}")
    
    return AlignmentResponse(
        total_elements=len(request.elements),
        aligned=aligned_count,
        unassigned=unassigned_count,
        results=results
    )


class AlignDocumentRequest(BaseModel):
    """Align DB-stored rows by document or chunks; persists to ParsedElement or DocumentChunk."""
    document_id: Optional[int] = Field(None, description="Align all elements of this document")
    chunk_ids: Optional[List[int]] = Field(None, description="Align these chunk IDs (DocumentChunk)")


@router.post("/align-document", response_model=AlignmentResponse)
async def align_document(request: AlignDocumentRequest, db: Session = Depends(get_db)):
    """
    Align document elements or chunks stored in DB and persist concept_id + alignment_confidence.
    Provide document_id to align ParsedElements, or chunk_ids to align DocumentChunks.
    """
    if not request.document_id and not request.chunk_ids:
        raise HTTPException(status_code=400, detail="Provide document_id or chunk_ids")
    all_results = []
    subject_id = None
    if request.document_id:
        doc = db.query(Document).filter(Document.id == request.document_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document {request.document_id} not found")
        subject_id = doc.subject_id
        elements_db = (
            db.query(ParsedElement)
            .filter(ParsedElement.document_id == request.document_id)
            .order_by(ParsedElement.order_index)
            .all()
        )
        # Build SemanticElement-like list (order, element_type, text)
        elements_for_align = [
            SemanticElement(
                order=e.order_index,
                element_type=e.element_type,
                text=e.text,
                page_number=e.page_number,
                source_filename=doc.filename or "",
                metadata={},
            )
            for e in elements_db
        ]
        if not elements_for_align:
            return AlignmentResponse(total_elements=0, aligned=0, unassigned=0, results=[])
        concepts = db.query(Concept).join(Unit).filter(Unit.subject_id == subject_id).all()
        if not concepts:
            raise HTTPException(status_code=404, detail=f"No concepts for subject_id={subject_id}")
        batch_results = await align_batch(elements_for_align, concepts)
        order_to_result = {r["order"]: r for r in batch_results}
        for e in elements_db:
            res = order_to_result.get(e.order_index, {})
            e.concept_id = res.get("concept_id")
            e.alignment_confidence = res.get("confidence")
        db.commit()
        all_results = batch_results
    if request.chunk_ids:
        chunks = db.query(DocumentChunk).filter(DocumentChunk.id.in_(request.chunk_ids)).all()
        if not chunks:
            raise HTTPException(status_code=404, detail="No chunks found for given chunk_ids")
        doc_id = chunks[0].document_id
        subject_id = db.query(Document).filter(Document.id == doc_id).first().subject_id
        # Use chunk_index as order, chunk text as content
        elements_for_align = [
            SemanticElement(
                order=c.chunk_index,
                element_type="CHUNK",
                text=c.text,
                page_number=c.page_start,
                source_filename="",
                metadata={},
            )
            for c in chunks
        ]
        concepts = db.query(Concept).join(Unit).filter(Unit.subject_id == subject_id).all()
        if not concepts:
            raise HTTPException(status_code=404, detail=f"No concepts for subject_id={subject_id}")
        batch_results = await align_batch(elements_for_align, concepts)
        chunk_index_to_result = {r["order"]: r for r in batch_results}
        for c in chunks:
            res = chunk_index_to_result.get(c.chunk_index, {})
            c.concept_id = res.get("concept_id")
            c.alignment_confidence = res.get("confidence")
        db.commit()
        # Update Qdrant payload so concept_id filter works
        try:
            qdrant = get_qdrant_manager()
            for c in chunks:
                if c.embedding_vector and c.vector_id:
                    payload = {
                        "subject_id": db.query(Document).filter(Document.id == c.document_id).first().subject_id,
                        "document_id": c.document_id,
                        "unit_id": c.unit_id,
                        "concept_id": c.concept_id,
                        "section_path": c.section_path or "",
                        "page_start": c.page_start or 0,
                        "page_end": c.page_end or 0,
                        "point_type": "chunk",
                        "chunk_id": c.id,
                    }
                    qdrant.client.upsert(
                        collection_name=qdrant.COLLECTION_NAME,
                        points=[
                            PointStruct(
                                id=c.id + qdrant.CHUNK_ID_OFFSET,
                                vector=c.embedding_vector,
                                payload=payload,
                            )
                        ],
                    )
        except Exception as e:
            print(f"⚠ Qdrant payload update for chunks failed: {str(e)}")
        all_results = batch_results if not all_results else all_results + batch_results
    aligned_count = sum(1 for r in all_results if r.get("concept_id") is not None)
    unassigned_count = len(all_results) - aligned_count
    results = [
        AlignmentResult(
            element_order=r["order"],
            concept_id=r.get("concept_id"),
            status="ALIGNED" if r.get("concept_id") else "UNASSIGNED",
            confidence=r.get("confidence"),
        )
        for r in all_results
    ]
    return AlignmentResponse(
        total_elements=len(all_results),
        aligned=aligned_count,
        unassigned=unassigned_count,
        results=results,
    )
