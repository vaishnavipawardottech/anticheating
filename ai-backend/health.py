"""
HEALTH CHECK API - FOUNDATION ONLY
No ingestion logic yet
Only service verification endpoints
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import os
import httpx
import asyncpg
from datetime import datetime

app = FastAPI(
    title="Academic Ingestion System - Health Checks",
    description="Structure-first academic ingestion engine - Infrastructure verification only",
    version="0.1.0"
)


@app.get("/health")
async def health_check():
    """
    Basic health check - API is running
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "academic-api"
    }


@app.get("/health/postgres")
async def postgres_health():
    """
    Verify Postgres connection (Structure DB)
    """
    try:
        conn = await asyncpg.connect(
            user=os.getenv("POSTGRES_USER", "academic_user"),
            password=os.getenv("POSTGRES_PASSWORD", "academic_pass"),
            database=os.getenv("POSTGRES_DB", "academic_structure"),
            host=os.getenv("POSTGRES_HOST", "postgres"),
            port=int(os.getenv("POSTGRES_PORT", "5432"))
        )
        version = await conn.fetchval("SELECT version()")
        await conn.close()
        
        return {
            "status": "healthy",
            "service": "postgres",
            "version": version.split(",")[0],
            "purpose": "Structure Database (Subject → Unit → Concept)"
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Postgres unhealthy: {str(e)}")


@app.get("/health/qdrant")
async def qdrant_health():
    """
    Verify Qdrant connection (Vector DB)
    """
    try:
        qdrant_host = os.getenv("QDRANT_HOST", "qdrant")
        qdrant_port = os.getenv("QDRANT_PORT", "6333")
        
        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://{qdrant_host}:{qdrant_port}/collections")
            response.raise_for_status()
            collections = response.json()
        
        return {
            "status": "healthy",
            "service": "qdrant",
            "collections": collections.get("result", {}).get("collections", []),
            "purpose": "Vector Database (Concept chunk embeddings only)"
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Qdrant unhealthy: {str(e)}")


@app.get("/health/ollama")
async def ollama_health():
    """
    Verify Ollama connection and Phi-3 Mini availability
    """
    try:
        ollama_host = os.getenv("OLLAMA_HOST", "ollama")
        ollama_port = os.getenv("OLLAMA_PORT", "11434")
        expected_model = os.getenv("OLLAMA_MODEL", "phi3:mini")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"http://{ollama_host}:{ollama_port}/api/tags")
            response.raise_for_status()
            data = response.json()
        
        models = [model["name"] for model in data.get("models", [])]
        phi3_available = any("phi3" in model for model in models)
        
        if not phi3_available:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unhealthy",
                    "service": "ollama",
                    "error": f"Required model '{expected_model}' not found",
                    "available_models": models,
                    "action": f"Run: docker exec academic_ollama ollama pull {expected_model}"
                }
            )
        
        return {
            "status": "healthy",
            "service": "ollama",
            "available_models": models,
            "required_model": expected_model,
            "model_ready": phi3_available,
            "purpose": "Local LLM (concept classification, ≤500 token context)"
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Ollama unhealthy: {str(e)}")


@app.get("/health/all")
async def all_services_health():
    """
    Check all services at once
    """
    results = {
        "api": {"status": "healthy"},
        "postgres": None,
        "qdrant": None,
        "ollama": None
    }
    
    overall_healthy = True
    
    # Check Postgres
    try:
        pg_result = await postgres_health()
        results["postgres"] = {"status": "healthy", "details": pg_result}
    except HTTPException as e:
        results["postgres"] = {"status": "unhealthy", "error": e.detail}
        overall_healthy = False
    
    # Check Qdrant
    try:
        qd_result = await qdrant_health()
        results["qdrant"] = {"status": "healthy", "details": qd_result}
    except HTTPException as e:
        results["qdrant"] = {"status": "unhealthy", "error": e.detail}
        overall_healthy = False
    
    # Check Ollama
    try:
        ol_result = await ollama_health()
        results["ollama"] = {"status": "healthy", "details": ol_result}
    except HTTPException as e:
        results["ollama"] = {"status": "unhealthy", "error": e.detail}
        overall_healthy = False
    
    return {
        "overall_status": "healthy" if overall_healthy else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "services": results
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
