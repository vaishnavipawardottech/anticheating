# ==========================================
# MINIMAL API CONTAINER - FOUNDATION ONLY
# No ingestion logic yet
# Only health checks and service verification
# ==========================================

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy minimal requirements
# Note: This will be expanded when ingestion logic is added
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose API port
EXPOSE 8000

# Health check endpoint only (no ingestion workers yet)
CMD ["uvicorn", "health:app", "--host", "0.0.0.0", "--port", "8000"]
