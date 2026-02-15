"""
Document Parsing Router
Endpoint for uploading and parsing documents (PDF, PPTX, DOCX)

Returns ordered semantic elements WITHOUT:
- Chunking
- Embeddings
- LLM classification
- Database writes
"""

import os
import tempfile
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, status, Query
from fastapi.responses import JSONResponse

from parsing.schemas import DocumentParseResponse, CleanupStatistics
from parsing.document_parser import DocumentParser
from parsing.cleanup import cleanup_elements

# Suppress verbose PDF color space warnings
logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("PIL").setLevel(logging.ERROR)

router = APIRouter(prefix="/documents", tags=["documents"])


# Configuration
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", 52428800))  # 50MB default
ALLOWED_EXTENSIONS = {"pdf", "pptx", "docx"}
MIME_TYPE_MAP = {
    "pdf": "application/pdf",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
}


def validate_file(file: UploadFile) -> tuple[str, str]:
    """
    Validate uploaded file
    
    Checks:
    - Has extension
    - Extension is allowed
    - Filename is valid
    
    Args:
        file: Uploaded file object
        
    Returns:
        Tuple of (filename, extension)
        
    Raises:
        HTTPException: If validation fails
    """
    # Ensure filename exists
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required"
        )
    
    # Normalize filename
    filename = file.filename.strip()
    
    # Extract extension
    file_path = Path(filename)
    extension = file_path.suffix.lower().lstrip(".")
    
    # Check if extension exists
    if not extension:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must have an extension"
        )
    
    # Check if extension is allowed
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: .{extension}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # Validate MIME type matches extension (don't trust MIME alone)
    expected_mime = MIME_TYPE_MAP.get(extension)
    if file.content_type and file.content_type != expected_mime:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"MIME type mismatch: expected {expected_mime}, got {file.content_type}"
        )
    
    return filename, extension


async def save_upload_file_tmp(upload_file: UploadFile, extension: str) -> tuple[str, int]:
    """
    Save uploaded file to temporary location
    
    Uses NamedTemporaryFile for safe temp file creation
    Validates file size during read
    
    Args:
        upload_file: FastAPI UploadFile object
        extension: File extension for temp file naming
        
    Returns:
        Tuple of (temp_file_path, file_size_bytes)
        
    Raises:
        HTTPException: If file is too large or save fails
    """
    try:
        # Create temp file with correct extension
        tmp = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=f".{extension}",
            prefix="upload_"
        )
        
        file_size = 0
        
        # Read and write in chunks to validate size
        chunk_size = 1024 * 1024  # 1MB chunks
        
        while True:
            chunk = await upload_file.read(chunk_size)
            if not chunk:
                break
            
            file_size += len(chunk)
            
            # Check size limit
            if file_size > MAX_UPLOAD_SIZE:
                tmp.close()
                os.unlink(tmp.name)  # Clean up
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File too large: {file_size} bytes. Max: {MAX_UPLOAD_SIZE} bytes ({MAX_UPLOAD_SIZE // 1048576}MB)"
                )
            
            tmp.write(chunk)
        
        tmp.close()
        return tmp.name, file_size
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save uploaded file: {str(e)}"
        )


@router.post("/parse")
async def parse_document(
    file: UploadFile = File(..., description="Document file (PDF, PPTX, DOCX)")
):
    """
    Parse uploaded document and extract semantic elements
    
    Supported formats: PDF, PPTX, DOCX
    Max file size: 50MB (configurable via MAX_UPLOAD_SIZE env var)
    
    All parsing results are automatically saved to parsing/output/ as JSON files.
    
    Returns ordered list of semantic elements:
    - Title, NarrativeText, ListItem, Image, Table, etc.
    - Preserves document order
    - Includes page numbers (when available)
    - Includes metadata (coordinates, detection confidence)
    
    This endpoint is DETERMINISTIC and ISOLATED:
    - No chunking
    - No embeddings
    - No LLM classification
    - No database writes
    
    Use this as the FIRST STEP in the ingestion pipeline.
    """
    temp_file_path = None
    
    try:
        # 1. Validate file
        filename, extension = validate_file(file)
        
        # 2. Save to temp file
        temp_file_path, file_size = await save_upload_file_tmp(file, extension)
        
        # Log file info
        print(f"📄 Parsing {filename} ({extension}, {file_size} bytes)")
        
        # 3. Parse document
        try:
            elements = DocumentParser.parse_document(temp_file_path, filename)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
        except RuntimeError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Document parsing failed: {str(e)}"
            )
        
        # 4. Get total pages (if available)
        # Re-parse raw elements to get page count
        from unstructured.partition.pdf import partition_pdf
        from unstructured.partition.pptx import partition_pptx
        from unstructured.partition.docx import partition_docx
        
        if extension == "pdf":
            raw_elements = partition_pdf(filename=temp_file_path, strategy="fast")
        elif extension == "pptx":
            raw_elements = partition_pptx(filename=temp_file_path)
        elif extension == "docx":
            raw_elements = partition_docx(filename=temp_file_path)
        else:
            raw_elements = []
        
        total_pages = DocumentParser.get_total_pages(raw_elements)
        
        # 4. Save all results to JSON file
        import json
        from datetime import datetime
        
        # Create output directory
        output_dir = Path("parsing/output").absolute()
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        safe_filename = Path(filename).stem.replace(" ", "_")
        output_filename = f"parsed_{safe_filename}_{timestamp}.json"
        output_path = output_dir / output_filename
        
        # Build full response data
        response_data = {
            "filename": filename,
            "file_type": extension,
            "file_size_bytes": file_size,
            "total_elements": len(elements),
            "total_pages": total_pages,
            "elements": [elem.model_dump() for elem in elements],
            "parsed_at": timestamp
        }
        
        # Write to JSON file
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(response_data, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Saved {len(elements)} elements to {output_path}")
        
        # Return summary
        return JSONResponse(content={
            "message": "Document parsed successfully",
            "filename": filename,
            "file_type": extension,
            "file_size_bytes": file_size,
            "total_elements": len(elements),
            "total_pages": total_pages,
            "output_file": str(output_path),
            "saved_at": timestamp
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error during parsing: {str(e)}"
        )
    
    finally:
        # 6. Always clean up temp file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
                print(f"🗑️  Cleaned up temp file: {temp_file_path}")
            except Exception as e:
                print(f"⚠️  Failed to delete temp file {temp_file_path}: {e}")


@router.post("/parse-and-cleanup")
async def parse_and_cleanup_document(
    file: UploadFile = File(..., description="Document file (PDF, PPTX, DOCX)")
):
    """
    Parse uploaded document and apply cleanup filters
    
    This endpoint combines parsing + cleanup in one step.
    
    Cleanup removes noise elements:
    - Headers/Footers
    - Page numbers
    - TOC dotted leaders
    - Pure numeric elements
    - Empty/whitespace-only elements
    - PDF CID encoding artifacts
    
    All cleanup is DETERMINISTIC (no AI/LLM).
    
    Returns cleaned semantic elements ready for alignment engine.
    """
    temp_file_path = None
    
    try:
        # 1. Validate file
        filename, extension = validate_file(file)
        
        # 2. Save to temp file
        temp_file_path, file_size = await save_upload_file_tmp(file, extension)
        
        # Log file info
        print(f"📄 Parsing and cleaning {filename} ({extension}, {file_size} bytes)")
        
        # 3. Parse document
        try:
            elements = DocumentParser.parse_document(temp_file_path, filename)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
        except RuntimeError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Document parsing failed: {str(e)}"
            )
        
        # 4. Apply cleanup filters
        cleanup_result = cleanup_elements(elements)
        cleaned_elements = cleanup_result.elements
        cleanup_stats = cleanup_result.statistics
        
        print(f"🧹 Cleanup: {cleanup_stats.removed_elements} removed, {cleanup_stats.kept_elements} kept")
        print(f"   Reasons: {cleanup_stats.removal_reasons}")
        
        # 5. Get total pages
        from unstructured.partition.pdf import partition_pdf
        from unstructured.partition.pptx import partition_pptx
        from unstructured.partition.docx import partition_docx
        
        if extension == "pdf":
            raw_elements = partition_pdf(filename=temp_file_path, strategy="fast")
        elif extension == "pptx":
            raw_elements = partition_pptx(filename=temp_file_path)
        elif extension == "docx":
            raw_elements = partition_docx(filename=temp_file_path)
        else:
            raw_elements = []
        
        total_pages = DocumentParser.get_total_pages(raw_elements)
        
        # 6. Build response
        response = DocumentParseResponse(
            filename=filename,
            file_type=extension,
            file_size_bytes=file_size,
            total_elements=len(cleaned_elements),
            total_pages=total_pages,
            elements=cleaned_elements,
            truncated=False,
            returned_elements=len(cleaned_elements),
            cleanup_applied=True,
            cleanup_statistics=CleanupStatistics(**cleanup_stats.to_dict())
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error during parsing: {str(e)}"
        )
    
    finally:
        # Always clean up temp file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
                print(f"🗑️  Cleaned up temp file: {temp_file_path}")
            except Exception as e:
                print(f"⚠️  Failed to delete temp file {temp_file_path}: {e}")


@router.get("/parse/supported-types")
def get_supported_types():
    """
    Get list of supported document types
    """
    return {
        "supported_extensions": list(ALLOWED_EXTENSIONS),
        "mime_types": MIME_TYPE_MAP,
        "max_file_size_bytes": MAX_UPLOAD_SIZE,
        "max_file_size_mb": MAX_UPLOAD_SIZE // 1048576
    }


@router.get("/health")
def health_check():
    """
    Check if document parsing dependencies are available
    """
    dependencies = {}
    
    # Check PDF support
    try:
        from unstructured.partition.pdf import partition_pdf
        dependencies["pdf"] = "available"
    except ImportError:
        dependencies["pdf"] = "missing - install: pip install unstructured[pdf]"
    
    # Check PPTX support
    try:
        from unstructured.partition.pptx import partition_pptx
        dependencies["pptx"] = "available"
    except ImportError:
        dependencies["pptx"] = "missing - install: pip install python-pptx"
    
    # Check DOCX support
    try:
        from unstructured.partition.docx import partition_docx
        dependencies["docx"] = "available"
    except ImportError:
        dependencies["docx"] = "missing - install: pip install python-docx"
    
    all_available = all(status == "available" for status in dependencies.values())
    
    return {
        "status": "healthy" if all_available else "degraded",
        "dependencies": dependencies,
        "max_upload_size_mb": MAX_UPLOAD_SIZE // 1048576
    }
