"""
Document Upload and Database Integration Endpoint  
Handles complete 10-step ingestion pipeline:
1. Parse (Unstructured)
2. Normalize (Unicode/text cleanup)
3. Caption Images (GPT-4o)
4. Format Tables (LLM → Markdown)
5. Cleanup (Remove noise)
6. Classify (TEXT/DIAGRAM/CODE)
7. Chunk (Section-aware, 600-1000 chars)
8. Embed (all-MiniLM-L6-v2)
9. Index (PostgreSQL + Qdrant)
10. Align (Gemini → Concepts)
"""

import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, status, Depends, Form, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

# New ingestion pipeline modules
from ingestion.parser import DocumentParser
from ingestion.normalizer import normalize_elements
from ingestion.image_captioner import caption_images
from ingestion.table_formatter import format_tables
from ingestion.cleanup import cleanup_elements
from ingestion.classifier import ElementClassifier
from ingestion.chunker import chunk_elements, compute_section_paths_for_elements, table_to_row_chunks
from ingestion.schemas import SemanticElement

from database.database import get_db
from database.models import Document, ParsedElement, DocumentChunk, Concept, Unit
from database.schemas import DocumentResponse, ParsedElementResponse
from embeddings import get_embedding_generator
from embeddings.qdrant_manager import get_qdrant_manager
from datetime import datetime
from qdrant_client.models import PointStruct

router = APIRouter(prefix="/documents", tags=["documents"])
def _parse_optional_document_id(document_id: Optional[str] = Query(None)) -> Optional[int]:
    """Parse document_id query param; treat missing or empty string as None to avoid 422."""
    if not document_id or not str(document_id).strip():
        return None
    try:
        return int(document_id)
    except ValueError:
        return None


# Configuration
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", 52428800))  # 50MB
ALLOWED_EXTENSIONS = {"pdf", "pptx", "docx"}
# DB may have section_path as VARCHAR(500); truncate so insert never fails. Run migrations/alter_section_path_to_text.py for TEXT.
MAX_SECTION_PATH_LEN = 500


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
    Complete 10-Step Ingestion Pipeline
    
    Steps:
    1. Parse document with Unstructured library (PDF/PPTX/DOCX)
    2. Normalize unicode & text (remove PDF artifacts, clean formatting)
    3. Caption images with GPT-4o Vision (generate text descriptions)
    4. Format tables with LLM (convert to clean Markdown)
    5. Cleanup (remove headers/footers/noise)
    6. Classify elements (TEXT/DIAGRAM/CODE/TABLE)
    7. Chunk content (600-1000 chars, 100 char overlap, section-aware)
    8. Generate embeddings (all-MiniLM-L6-v2, 384-dim)
    9. Index to storage (PostgreSQL + Qdrant vector DB)
    10. Align chunks to concepts (Gemini AI classification)
    
    Returns document metadata with processing status
    
    Status flow: uploading → parsing → embedding → indexing → indexed
    """
    saved_file_path = None
    
    try:
        # 1. Validate file
        filename, extension = validate_file(file)
        
        print(f"Processing {filename} ({extension})")
        
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
            print(f"   Step 1: Parsed {len(elements)} elements")
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
        
        # 5. Normalize unicode and text (NEW - Step 2)
        elements = normalize_elements(elements)
        print(f"   Step 2: Text normalized")
        
        # 6. Caption images with GPT-4o (NEW - Step 3)
        try:
            elements = await caption_images(elements, saved_file_path)
            print(f"   Step 3: Images captioned")
        except Exception as e:
            print(f"   Step 3: Image captioning failed: {str(e)}")
            # Continue without image captions
        
        # 7. Format tables to Markdown (NEW - Step 4)
        try:
            elements = await format_tables(elements, saved_file_path)
            print(f"   Step 4: Tables formatted")
        except Exception as e:
            print(f"   Step 4: Table formatting failed: {str(e)}")
            # Continue with original table text
        
        # 8. Apply cleanup filters (Step 5)
        cleanup_result = cleanup_elements(elements)
        cleaned_elements = cleanup_result.elements
        cleanup_stats = cleanup_result.statistics
        
        print(f"   Step 5: Cleanup - {cleanup_stats.removed_elements} removed, {cleanup_stats.kept_elements} kept")
        
        # 9. Classify elements (Step 6)
        classifier = ElementClassifier()
        for element in cleaned_elements:
            element.category = classifier.classify(element)
            element.is_diagram_critical = classifier.is_diagram_critical(element)
        
        # Count by category
        category_counts = {}
        for element in cleaned_elements:
            cat = getattr(element, 'category', 'OTHER')
            category_counts[cat] = category_counts.get(cat, 0) + 1
        
        print(f"   Step 6: Classification - {category_counts}")
        
        # Step 6b: Section paths for metadata (heading stack → section_path)
        section_paths = compute_section_paths_for_elements(cleaned_elements)

        # Step 7: Semantic chunking (600-1000 chars, 100 overlap)
        try:
            emb_gen = get_embedding_generator()
            embed_fn = emb_gen.generate_embeddings_batch
        except Exception:
            embed_fn = None
        doc_chunks = chunk_elements(cleaned_elements, section_paths=section_paths, embed_fn=embed_fn)
        for idx, element in enumerate(cleaned_elements):
            if getattr(element, "category", "OTHER") == "TABLE" and element.text:
                path = section_paths[idx] if idx < len(section_paths) else ""
                page = getattr(element, "page_number", None) or 1
                doc_chunks.extend(table_to_row_chunks(element.text, path, page, idx))
        doc_chunks.sort(key=lambda c: (c.page_start or 0, c.source_element_orders[0] if c.source_element_orders else 0))
        print(f"   Step 7: Chunking - {len(doc_chunks)} chunks from {len(cleaned_elements)} elements")
        
        # Step 8: Generate embeddings for TEXT elements
        document.status = "embedding"
        db.commit()
        
        # Build (index, text) list for TEXT elements in one pass (avoid O(n²) and wrong index for duplicates)
        text_indices_and_texts = [
            (idx, elem.text)
            for idx, elem in enumerate(cleaned_elements)
            if getattr(elem, 'category', 'OTHER') == 'TEXT' and elem.text and elem.text.strip()
        ]
        
        embeddings_map = {}  # Map element index to embedding
        
        if text_indices_and_texts:
            indices = [t[0] for t in text_indices_and_texts]
            texts = [t[1] for t in text_indices_and_texts]
            
            try:
                embedding_gen = get_embedding_generator()
                embeddings = embedding_gen.generate_embeddings_batch(texts, batch_size=32)
                
                for stored_idx, embedding in zip(indices, embeddings):
                    embeddings_map[stored_idx] = embedding
                
                print(f"   Step 8: Generated {len(embeddings)} embeddings ({embedding_gen.EMBEDDING_DIM}-dim)")
                
            except Exception as e:
                print(f"   Step 8: Embedding generation failed: {str(e)}")
                print(f"   Continuing without embeddings...")
        else:
            print(f"   Step 8: No TEXT elements to embed")
        
        # Step 9a: Save elements to database (with section_path per element)
        for idx, element in enumerate(cleaned_elements):
            sp = section_paths[idx] if idx < len(section_paths) else None
            if sp and len(sp) > MAX_SECTION_PATH_LEN:
                sp = sp[: MAX_SECTION_PATH_LEN - 3] + "..."
            db_element = ParsedElement(
                document_id=document.id,
                order_index=idx,
                element_type=element.element_type,
                category=getattr(element, 'category', 'OTHER'),
                text=element.text,
                page_number=element.page_number,
                section_path=sp or None,
                element_metadata=element.metadata,
                is_diagram_critical=getattr(element, 'is_diagram_critical', False),
                confidence_score=None,
                embedding_vector=embeddings_map.get(idx)  # Add embedding if available
            )
            db.add(db_element)
        
        db.commit()  # Commit to get element IDs
        print(f"   Saved {len(cleaned_elements)} elements to database")
        if embeddings_map:
            print(f"   ({len(embeddings_map)} elements with embeddings)")
        
        # Step 9b: Index embeddings to Qdrant (vector search)
        if embeddings_map:
            document.status = "indexing"
            db.commit()
            
            try:
                qdrant = get_qdrant_manager()
                qdrant.create_collection()  # ensure collection exists before indexing
                
                # Get saved elements with embeddings
                saved_elements = db.query(ParsedElement)\
                    .filter(ParsedElement.document_id == document.id)\
                    .filter(ParsedElement.embedding_vector.isnot(None))\
                    .order_by(ParsedElement.order_index)\
                    .all()
                
                # Prepare batch data for Qdrant
                element_ids = []
                embeddings_list = []
                metadatas = []
                
                # Get expected dimension
                emb_gen = get_embedding_generator()
                expected_dim = emb_gen.EMBEDDING_DIM
                
                for elem in saved_elements:
                    ev = elem.embedding_vector
                    if ev is None or not isinstance(ev, list) or len(ev) != expected_dim:
                        continue
                    element_ids.append(elem.id)
                    embeddings_list.append(ev)
                    metadatas.append({
                        "document_id": document.id,
                        "subject_id": subject_id,
                        "category": elem.category,
                        "page_number": elem.page_number or 0,
                        "element_type": elem.element_type
                    })
                
                # Batch index to Qdrant
                vector_ids = qdrant.index_elements_batch(
                    element_ids, embeddings_list, metadatas
                )
                
                # Update database with vector_ids and indexed_at
                emb_model = get_embedding_generator()
                model_name = emb_model.model_name
                dim = emb_model.EMBEDDING_DIM
                now = datetime.now()
                for elem_id, vector_id in zip(element_ids, vector_ids):
                    elem = db.query(ParsedElement).get(elem_id)
                    elem.vector_id = vector_id
                    elem.indexed_at = now
                    elem.embedding_model = model_name
                    elem.embedding_dim = dim
                    elem.embedded_at = now
                
                db.commit()
                print(f"   Indexed {len(vector_ids)} vectors to Qdrant")
                
            except Exception as e:
                print(f"   Qdrant indexing failed: {str(e)}")
                print(f"   Continuing without vector indexing (embeddings saved in DB)...")
        
        # 9b. Save and index chunks (section-aware retrieval)
        if doc_chunks:
            for chunk_index, cinfo in enumerate(doc_chunks):
                # section_path can be very long in slide decks; truncate so VARCHAR(500) never exceeded
                sp = (cinfo.section_path or "").strip() or None
                if sp and len(sp) > MAX_SECTION_PATH_LEN:
                    sp = sp[: MAX_SECTION_PATH_LEN - 3] + "..."
                token_count = int(len((cinfo.text or "").split()) * 1.3)
                db_chunk = DocumentChunk(
                    document_id=document.id,
                    chunk_index=chunk_index,
                    text=cinfo.text,
                    section_path=sp,
                    page_start=cinfo.page_start,
                    page_end=cinfo.page_end,
                    source_element_orders=cinfo.source_element_orders,
                    token_count=token_count,
                    chunk_type=getattr(cinfo, "chunk_type", "text"),
                    table_id=getattr(cinfo, "table_id", None),
                    row_id=getattr(cinfo, "row_id", None),
                    unit_id=None,
                    concept_id=None,
                )
                db.add(db_chunk)
            db.commit()
            # Get chunk IDs and generate chunk embeddings
            saved_chunks = db.query(DocumentChunk).filter(
                DocumentChunk.document_id == document.id
            ).order_by(DocumentChunk.chunk_index).all()
            chunk_texts = [c.text for c in saved_chunks]
            try:
                embedding_gen = get_embedding_generator()
                chunk_embeddings = embedding_gen.generate_embeddings_batch(chunk_texts, batch_size=32)
                chunk_ids = []
                embeddings_list = []
                metadatas = []
                emb_model = get_embedding_generator()
                model_name = emb_model.model_name
                dim = emb_model.EMBEDDING_DIM
                now = datetime.now()
                expected_dim = dim  # Already fetched above
                for c, emb in zip(saved_chunks, chunk_embeddings):
                    c.embedding_vector = emb
                    if emb is None or not isinstance(emb, list) or len(emb) != expected_dim:
                        continue
                    chunk_ids.append(c.id)
                    embeddings_list.append(emb)
                    sp = (c.section_path or "")[:MAX_SECTION_PATH_LEN]
                    meta = {
                        "subject_id": subject_id,
                        "document_id": document.id,
                        "unit_id": c.unit_id,
                        "concept_id": c.concept_id,
                        "section_path": sp,
                        "page_start": c.page_start or 0,
                        "page_end": c.page_end or 0,
                        "point_type": "chunk",
                        "chunk_type": getattr(c, "chunk_type", "text") or "text",
                    }
                    if getattr(c, "table_id", None) is not None:
                        meta["table_id"] = c.table_id
                    if getattr(c, "row_id", None) is not None:
                        meta["row_id"] = c.row_id
                    metadatas.append(meta)
                if chunk_ids:
                    db.commit()
                    qdrant = get_qdrant_manager()
                    qdrant.index_chunks_batch(chunk_ids, embeddings_list, metadatas)
                    indexed_chunk_ids = set(chunk_ids)
                    for c in saved_chunks:
                        if c.id in indexed_chunk_ids:
                            c.vector_id = f"chunk_{c.id}"
                            c.indexed_at = now
                            c.embedding_model = model_name
                            c.embedding_dim = dim
                            c.embedded_at = now
                    db.commit()
                    print(f"   Indexed {len(chunk_ids)} chunks to Qdrant")
                else:
                    db.commit()  # persist embedding_vector on chunks even when not indexing
                    print(f"   No chunk embeddings to index (skipped)")
            except Exception as e:
                print(f"   Chunk embedding/indexing failed: {str(e)}")
        
        # Step 10: Auto-align chunks to concepts (AI-powered with Gemini)
        if doc_chunks and saved_chunks:
            try:
                print(f"   Step 10: Auto-aligning chunks to concepts...")
                
                # Get concepts for this subject
                concepts = db.query(Concept).join(Unit).filter(Unit.subject_id == subject_id).all()
                
                if concepts:
                    # Import align_batch here to avoid circular dependency
                    from routers.alignment import align_batch
                    
                    # Prepare chunks as SemanticElements for alignment
                    elements_for_align = [
                        SemanticElement(
                            order=c.chunk_index,
                            element_type="CHUNK",
                            text=c.text,
                            page_number=c.page_start,
                            source_filename=filename,
                            metadata={},
                        )
                        for c in saved_chunks
                    ]
                    
                    # Call Gemini AI to align chunks
                    batch_results = await align_batch(elements_for_align, concepts)
                    chunk_index_to_result = {r["order"]: r for r in batch_results}
                    
                    # Build concept_id -> unit_id mapping
                    concept_to_unit = {concept.id: concept.unit_id for concept in concepts}
                    
                    # Update chunks with alignment results
                    aligned_count = 0
                    for c in saved_chunks:
                        res = chunk_index_to_result.get(c.chunk_index, {})
                        concept_id = res.get("concept_id")
                        c.concept_id = concept_id
                        c.alignment_confidence = res.get("confidence")
                        
                        # Automatically set unit_id from concept's parent unit
                        if concept_id and concept_id in concept_to_unit:
                            c.unit_id = concept_to_unit[concept_id]
                            aligned_count += 1
                    
                    db.commit()
                    
                    # Update Qdrant payloads with concept_id and unit_id (metadata only)
                    try:
                        qdrant = get_qdrant_manager()
                        point_ids = []
                        for c in saved_chunks:
                            # Only need chunk to be indexed (has vector_id)
                            if c.vector_id:
                                point_ids.append(c.id + qdrant.CHUNK_ID_OFFSET)
                        
                        # Update payloads in batch (more efficient than upserting entire vectors)
                        for c in saved_chunks:
                            if c.vector_id:
                                sp = (c.section_path or "")[:MAX_SECTION_PATH_LEN]
                                payload = {
                                    "subject_id": subject_id,
                                    "document_id": c.document_id,
                                    "unit_id": c.unit_id,
                                    "concept_id": c.concept_id,
                                    "section_path": sp,
                                    "page_start": c.page_start or 0,
                                    "page_end": c.page_end or 0,
                                    "point_type": "chunk",
                                    "chunk_type": c.chunk_type or "text",
                                    "chunk_id": c.id,
                                }
                                qdrant.client.set_payload(
                                    collection_name=qdrant.COLLECTION_CHUNKS,
                                    payload=payload,
                                    points=[c.id + qdrant.CHUNK_ID_OFFSET],
                                )
                        print(f"   Step 10: Aligned {aligned_count}/{len(saved_chunks)} chunks, updated Qdrant payloads")
                    except Exception as qdrant_err:
                        print(f"   Qdrant payload update failed: {str(qdrant_err)}")
                        print(f"   Alignment saved to database, but Qdrant filtering may not work")
                else:
                    print(f"   Step 10: No concepts found for subject_id={subject_id}, skipping alignment")
                    
            except Exception as align_err:
                print(f"   Step 10: Alignment failed - {str(align_err)}")
                print(f"   Document ingested successfully, but chunks not aligned")
                import traceback
                traceback.print_exc()
        
        # 10. Update document status
        document.status = "indexed" if embeddings_map else "parsed"
        db.commit()
        
        print(f"Document processing complete: {filename}")
        
        return document
        
    except HTTPException:
        # If we created a file, keep it for debugging
        # User can delete it manually if needed
        raise
    except Exception as e:
        # Rollback database changes
        db.rollback()
        
        # Log full error traceback
        import traceback
        error_traceback = traceback.format_exc()
        print(f"ERROR during document processing:")
        print(error_traceback)
        
        # Keep file for debugging
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )


@router.get("/embedding-status")
def get_embedding_status(
    document_id: Optional[int] = Depends(_parse_optional_document_id),
    db: Session = Depends(get_db),
):
    """
    Summary of embedding status: total/embedded/missing for elements and chunks,
    optional document filter, and doc-level badges (X/Y embedded + model name).
    """
    # Elements
    elem_base = db.query(ParsedElement).filter(ParsedElement.document_id == document_id) if document_id else db.query(ParsedElement)
    total_elements = elem_base.count()
    embedded_elements = elem_base.filter(ParsedElement.vector_id.isnot(None)).count()

    # Chunks
    chunk_base = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id) if document_id else db.query(DocumentChunk)
    total_chunks = chunk_base.count()
    embedded_chunks = chunk_base.filter(DocumentChunk.vector_id.isnot(None)).count()

    # Model name from first embedded row or generator
    model_name = None
    first_emb = db.query(ParsedElement.embedding_model).filter(ParsedElement.embedding_model.isnot(None)).first()
    if first_emb and first_emb[0]:
        model_name = first_emb[0]
    else:
        first_chunk = db.query(DocumentChunk.embedding_model).filter(DocumentChunk.embedding_model.isnot(None)).first()
        if first_chunk and first_chunk[0]:
            model_name = first_chunk[0]
    if not model_name:
        try:
            model_name = get_embedding_generator().model_name
        except Exception:
            model_name = "unknown"

    by_document = []
    docs = db.query(Document).filter(Document.id == document_id).all() if document_id else db.query(Document).all()
    for doc in docs:
        e_tot = db.query(ParsedElement).filter(ParsedElement.document_id == doc.id).count()
        e_emb = db.query(ParsedElement).filter(ParsedElement.document_id == doc.id, ParsedElement.vector_id.isnot(None)).count()
        c_tot = db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).count()
        c_emb = db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id, DocumentChunk.vector_id.isnot(None)).count()
        by_document.append({
            "document_id": doc.id,
            "filename": doc.filename,
            "elements_total": e_tot,
            "elements_embedded": e_emb,
            "elements_missing": e_tot - e_emb,
            "chunks_total": c_tot,
            "chunks_embedded": c_emb,
            "chunks_missing": c_tot - c_emb,
            "badge": f"{c_emb}/{c_tot} chunks" + (" [OK]" if c_tot and c_emb == c_tot else ""),
        })

    return {
        "embedding_model": model_name,
        "total_elements": total_elements,
        "embedded_elements": embedded_elements,
        "missing_elements": total_elements - embedded_elements,
        "total_chunks": total_chunks,
        "embedded_chunks": embedded_chunks,
        "missing_chunks": total_chunks - embedded_chunks,
        "by_document": by_document,
    }


@router.get("/elements-with-embeddings")
def get_elements_with_embeddings(
    document_id: Optional[int] = Depends(_parse_optional_document_id),
    limit: int = 100,
    offset: int = 0,
    unembedded_only: bool = False,
    embedded_before: Optional[str] = None,
    category: Optional[str] = None,
    element_type: Optional[str] = None,
    text_mode: str = Query("preview", description="preview (first 200 chars) or full"),
    db: Session = Depends(get_db),
):
    """
    List parsed elements with optional filters.
    text_mode: preview (default) or full — full includes full text in each element.
    unembedded_only: only elements without vector_id.
    embedded_before: ISO date string (e.g. 2025-01-01) for stale embeddings.
    category: TEXT, DIAGRAM, TABLE, etc.
    element_type: Title, NarrativeText, ListItem, etc. (comma-separated for multiple).
    """
    query = db.query(ParsedElement).order_by(ParsedElement.document_id, ParsedElement.order_index)
    if document_id is not None:
        query = query.filter(ParsedElement.document_id == document_id)
    if unembedded_only:
        query = query.filter(ParsedElement.vector_id.is_(None))
    else:
        query = query.filter(ParsedElement.embedding_vector.isnot(None))
    if embedded_before:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(embedded_before.replace("Z", "+00:00"))
            query = query.filter(ParsedElement.embedded_at < dt)
        except Exception:
            pass
    if category:
        query = query.filter(ParsedElement.category == category)
    if element_type:
        types = [t.strip() for t in element_type.split(",") if t.strip()]
        if types:
            query = query.filter(ParsedElement.element_type.in_(types))
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    out = []
    for e in rows:
        ev = e.embedding_vector
        embed_dim = len(ev) if isinstance(ev, list) else None
        text_preview = (e.text or "")[:200].strip() or None
        item = {
            "id": e.id,
            "document_id": e.document_id,
            "order_index": e.order_index,
            "text_preview": text_preview,
            "element_type": e.element_type,
            "category": e.category,
            "section_path": (e.section_path or "")[:100] if getattr(e, "section_path", None) else None,
            "vector_id": e.vector_id,
            "embed_dim": embed_dim,
            "embedding_model": getattr(e, "embedding_model", None),
            "embedded_at": getattr(e, "embedded_at", None),
        }
        if text_mode == "full":
            item["text"] = (e.text or "").strip() or None
        out.append(item)
    return {
        "total": total,
        "returned": len(out),
        "offset": offset,
        "limit": limit,
        "elements": out,
    }


@router.get("/chunks-with-embeddings")
def get_chunks_with_embeddings(
    document_id: Optional[int] = Depends(_parse_optional_document_id),
    limit: int = 100,
    offset: int = 0,
    text_mode: str = Query("preview", description="preview (first 200 chars) or full"),
    db: Session = Depends(get_db)
):
    """
    List document chunks that have embeddings: text preview, section_path, vector_id, embed dim.
    text_mode: preview (default) or full — full includes full text in each chunk.
    Optional document_id to filter by document.
    """
    query = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.embedding_vector.isnot(None))
        .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
    )
    if document_id is not None:
        query = query.filter(DocumentChunk.document_id == document_id)
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    out = []
    for c in rows:
        ev = c.embedding_vector
        embed_dim = len(ev) if isinstance(ev, list) else None
        text_preview = (c.text or "")[:200].strip() or None
        item = {
            "id": c.id,
            "document_id": c.document_id,
            "chunk_index": c.chunk_index,
            "text_preview": text_preview,
            "section_path": (c.section_path or "")[:150],
            "page_start": c.page_start,
            "page_end": c.page_end,
            "vector_id": c.vector_id,
            "embed_dim": embed_dim,
            "unit_id": c.unit_id,
            "concept_id": c.concept_id,
        }
        if text_mode == "full":
            item["text"] = (c.text or "").strip() or None
        out.append(item)
    return {
        "total": total,
        "returned": len(out),
        "offset": offset,
        "limit": limit,
        "chunks": out,
    }


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: int, db: Session = Depends(get_db)):
    """Get document by ID"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found"
        )
    return document


@router.get("/{document_id}/elements")
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


@router.delete("/{document_id}")
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
        print(f"Deleted vectors for document {document_id} from Qdrant")
    except Exception as e:
        print(f"Qdrant cleanup failed: {str(e)}")
        # Continue with database deletion even if Qdrant fails
    
    # Delete file if it exists
    if document.file_path and os.path.exists(document.file_path):
        try:
            os.remove(document.file_path)
            print(f"Deleted file: {document.file_path}")
        except Exception as e:
            print(f"File deletion failed: {str(e)}")
    
    # Delete chunks and elements first so FK is never set to NULL (avoids NotNullViolation)
    db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
    db.query(ParsedElement).filter(ParsedElement.document_id == document_id).delete()
    db.delete(document)
    db.commit()
    
    return {"message": f"Document {document_id} deleted successfully"}
