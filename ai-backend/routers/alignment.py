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
from database.models import Concept, Unit, AlignedElement
from parsing.schemas import SemanticElement
from routers.structure_ai import call_gemini_flash

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
