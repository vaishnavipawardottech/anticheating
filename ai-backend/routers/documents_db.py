"""
Document Upload and Database Integration Endpoint
Handles complete pipeline: Upload → Parse → Cleanup → Classify → Embed → Index to Qdrant
"""

import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, status, Depends, Form
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from parsing.document_parser import DocumentParser
from parsing.cleanup import cleanup_elements
from parsing.classifier import ElementClassifier
from database.database import get_db
from database.models import Document, ParsedElement
from database.schemas import DocumentResponse, ParsedElementResponse
from embeddings import get_embedding_generator
from embeddings.qdrant_manager import get_qdrant_manager
from datetime import datetime

router = APIRouter(prefix="/documents", tags=["documents"])

# Configuration
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", 52428800))  # 50MB
ALLOWED_EXTENSIONS = {"pdf", "pptx", "docx"}


def validate_file(file: UploadFile) -> tuple[str, str]:
    """Validate uploaded file"""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required"
        )
    
    filename = file.filename.strip()
    file_path = Path(filename)
    extension = file_path.suffix.lower().lstrip(".")
    
    if not extension:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must have an extension"
        )
    
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: .{extension}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    return filename, extension


async def save_upload_file_permanent(upload_file: UploadFile, extension: str, document_id: int) -> tuple[str, int]:
    """
    Save uploaded file to permanent storage
    
    Args:
        upload_file: FastAPI UploadFile object
        extension: File extension
        document_id: Document ID for organizing files
        
    Returns:
        Tuple of (file_path, file_size_bytes)
    """
    try:
        # Create uploads directory if it doesn't exist
        uploads_dir = Path("uploads")
        uploads_dir.mkdir(exist_ok=True)
        
        # Generate unique filename: doc_{id}_{timestamp}.{ext}
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"doc_{document_id}_{timestamp}.{extension}"
        file_path = uploads_dir / filename
        
        file_size = 0
        chunk_size = 1024 * 1024  # 1MB chunks
        
        # Write file in chunks
        with open(file_path, "wb") as f:
            while True:
                chunk = await upload_file.read(chunk_size)
                if not chunk:
                    break
                
                file_size += len(chunk)
                
                # Check size limit
                if file_size > MAX_UPLOAD_SIZE:
                    # Delete partial file
                    if file_path.exists():
                        file_path.unlink()
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File too large: {file_size} bytes. Max: {MAX_UPLOAD_SIZE} bytes"
                    )
                
                f.write(chunk)
        
        return str(file_path), file_size
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save uploaded file: {str(e)}"
        )


@router.post("/upload-and-store", response_model=DocumentResponse)
async def upload_and_store_document(
    file: UploadFile = File(..., description="Document file (PDF, PPTX, DOCX)"),
    subject_id: int = Form(..., description="Subject ID to link document to"),
    db: Session = Depends(get_db)
):
    """
    Complete pipeline: Upload → Parse → Cleanup → Classify → Embed → Index to Qdrant
    
    Steps:
    1. Validate file
    2. Create document record (to get ID)
    3. Save file permanently with document ID in filename
    4. Parse with Unstructured library
    5. Apply cleanup filters
    6. Classify elements
    7. Generate embeddings for TEXT elements
    8. Save elements to database
    9. Index embeddings to Qdrant
    10. Update document status
    
    Returns document metadata with processing status
    
    Status flow: uploading → parsing → embedding → indexing → indexed
    """
    saved_file_path = None
    
    try:
        # 1. Validate file
        filename, extension = validate_file(file)
        
        print(f"📄 Processing {filename} ({extension})")
        
        # 2. Create document record first (to get ID for filename)
        document = Document(
            filename=filename,
            file_type=extension,
            file_size_bytes=0,  # Will update after saving
            subject_id=subject_id,
            status="uploading"
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        
        # 3. Save file permanently with document ID
        saved_file_path, file_size = await save_upload_file_permanent(file, extension, document.id)
        
        # Update document with file size, path, and status
        document.file_size_bytes = file_size
        document.file_path = saved_file_path
        document.status = "parsing"
        db.commit()
        
        print(f"   Saved to: {saved_file_path} ({file_size} bytes)")
        
        # 4. Parse document
        try:
            elements = DocumentParser.parse_document(saved_file_path, filename)
            print(f"   Parsed {len(elements)} elements")
        except ValueError as e:
            document.status = "failed"
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
        except RuntimeError as e:
            document.status = "failed"
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Document parsing failed: {str(e)}"
            )
        
        # 5. Apply cleanup filters
        cleanup_result = cleanup_elements(elements)
        cleaned_elements = cleanup_result.elements
        cleanup_stats = cleanup_result.statistics
        
        print(f"   Cleanup: {cleanup_stats.removed_elements} removed, {cleanup_stats.kept_elements} kept")
        
        # 6. Classify elements (compute categories for database storage)
        print(f"   Classifying {len(cleaned_elements)} elements...")
        classifier = ElementClassifier()
        
        # Create a map of element index to classification results
        classification_map = {}
        for idx, element in enumerate(cleaned_elements):
            category = classifier.classify(element)
            is_diagram_critical = classifier.is_diagram_critical(element)
            classification_map[idx] = {
                'category': category,
                'is_diagram_critical': is_diagram_critical
            }
        
        # Count by category
        category_counts = {}
        for classification in classification_map.values():
            cat = classification['category']
            category_counts[cat] = category_counts.get(cat, 0) + 1
        
        print(f"   Classification: {category_counts}")
        
        # 7. Generate embeddings for TEXT elements
        document.status = "embedding"
        db.commit()
        
        # Filter TEXT elements that have content
        text_elements_indices = [
            idx for idx, classification in classification_map.items()
            if classification['category'] == 'TEXT' 
            and cleaned_elements[idx].text 
            and cleaned_elements[idx].text.strip()
        ]
        
        embeddings_map = {}  # Map element index to embedding
        
        if text_elements_indices:
            print(f"   Generating embeddings for {len(text_elements_indices)} TEXT elements...")
            
            try:
                # Get embedding generator
                embedding_gen = get_embedding_generator()
                
                # Extract texts for batch processing
                texts = [cleaned_elements[idx].text for idx in text_elements_indices]
                
                # Generate embeddings in batch (efficient)
                embeddings = embedding_gen.generate_embeddings_batch(texts, batch_size=32)
                
                # Map embeddings back to element indices
                for idx, embedding in zip(text_elements_indices, embeddings):
                    embeddings_map[idx] = embedding
                
                print(f"   ✓ Generated {len(embeddings)} embeddings (384-dim each)")
                
            except Exception as e:
                print(f"   ⚠ Warning: Embedding generation failed: {str(e)}")
                print(f"   Continuing without embeddings...")
        else:
            print(f"   No TEXT elements to embed")
        
        # 8. Save elements to database
        for idx, element in enumerate(cleaned_elements):
            classification = classification_map[idx]
            db_element = ParsedElement(
                document_id=document.id,
                order_index=idx,
                element_type=element.element_type,
                category=classification['category'],
                text=element.text,
                page_number=element.page_number,
                element_metadata=element.metadata,
                is_diagram_critical=classification['is_diagram_critical'],
                confidence_score=None,
                embedding_vector=embeddings_map.get(idx)  # Add embedding if available
            )
            db.add(db_element)
        
        db.commit()  # Commit to get element IDs
        print(f"   Saved {len(cleaned_elements)} elements to database")
        if embeddings_map:
            print(f"   ({len(embeddings_map)} elements with embeddings)")

        # 9. Index embeddings to Qdrant
        if embeddings_map:
            document.status = "indexing"
            db.commit()
            
            try:
                qdrant = get_qdrant_manager()
                
                # Get saved elements with embeddings
                saved_elements = db.query(ParsedElement)\
                    .filter(ParsedElement.document_id == document.id)\
                    .filter(ParsedElement.embedding_vector.isnot(None))\
                    .order_by(ParsedElement.order_index)\
                    .all()
                
                if saved_elements:
                    # Prepare batch data for Qdrant
                    element_ids = []
                    embeddings_list = []
                    metadatas = []
                    
                    for elem in saved_elements:
                        element_ids.append(elem.id)
                        embeddings_list.append(elem.embedding_vector)
                        metadatas.append({
                            "document_id": document.id,
                            "subject_id": subject_id,
                            "category": elem.category,
                            "page_number": elem.page_number or 0,
                            "element_type": elem.element_type
                        })
                    
                    print(f"   Indexing {len(saved_elements)} vectors to Qdrant...")
                    
                    # Batch index to Qdrant
                    vector_ids = qdrant.index_elements_batch(
                        element_ids, embeddings_list, metadatas
                    )
                    
                    # Update database with vector_ids and indexed_at
                    for elem_id, vector_id in zip(element_ids, vector_ids):
                        elem = db.query(ParsedElement).filter(ParsedElement.id == elem_id).first()
                        if elem:
                            elem.vector_id = str(vector_id)
                            elem.indexed_at = func.now()
                    
                    db.commit()
                    print(f"   ✓ Indexed {len(vector_ids)} vectors to Qdrant")
                
                # Mark document as indexed
                document.status = "indexed"
                document.indexed_at = func.now()
                db.commit()
                
            except Exception as e:
                print(f"   ⚠ Qdrant indexing failed: {str(e)}")
                print(f"   Continuing without vector indexing (embeddings saved in DB)...")
                # Still mark as indexed even if Qdrant fails
                document.status = "indexed"
                db.commit()
        else:
            # No embeddings generated, still mark as complete
            document.status = "indexed"
            db.commit()
        
        print(f"✓ Document processing complete: {filename}")
        
        return document
        
    except HTTPException:
        # If we created a file, keep it for debugging
        # User can delete it manually if needed
        raise
    except Exception as e:
        # Rollback database changes
        db.rollback()
        
        # Keep file for debugging
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )


@router.get("/documents/{document_id}", response_model=DocumentResponse)
def get_document(document_id: int, db: Session = Depends(get_db)):
    """Get document by ID"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found"
        )
    return document


@router.get("/documents/{document_id}/elements")
def get_document_elements(
    document_id: int,
    category: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Get parsed elements for a document"""
    # Check document exists
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found"
        )
    
    # Build query
    query = db.query(ParsedElement).filter(ParsedElement.document_id == document_id)
    
    # Filter by category if specified
    if category:
        query = query.filter(ParsedElement.category == category)
    
    # Order by position in document
    query = query.order_by(ParsedElement.order_index)
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    elements = query.offset(offset).limit(limit).all()
    
    return {
        "document_id": document_id,
        "total_elements": total,
        "returned_elements": len(elements),
        "offset": offset,
        "limit": limit,
        "elements": elements
    }


@router.delete("/documents/{document_id}")
def delete_document(document_id: int, db: Session = Depends(get_db)):
    """Delete document and cleanup vectors from Qdrant"""
    
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found"
        )
    
    # Delete vectors from Qdrant
    try:
        qdrant = get_qdrant_manager()
        qdrant.delete_by_document(document_id)
        print(f"✓ Deleted vectors for document {document_id} from Qdrant")
    except Exception as e:
        print(f"⚠ Qdrant cleanup failed: {str(e)}")
        # Continue with database deletion even if Qdrant fails
    
    # Delete file if it exists
    if document.file_path and os.path.exists(document.file_path):
        try:
            os.remove(document.file_path)
            print(f"✓ Deleted file: {document.file_path}")
        except Exception as e:
            print(f"⚠ File deletion failed: {str(e)}")
    
    # Delete from database (cascade deletes elements)
    db.delete(document)
    db.commit()
    
    return {"message": f"Document {document_id} deleted successfully"}
