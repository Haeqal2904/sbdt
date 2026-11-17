# ==========================================
# STAGE 1: Builder Stage
# ==========================================
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies for compiling Python extensions (e.g. psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy model training script and execute it to generate model artifact
COPY train_model.py .
RUN python train_model.py

# ==========================================
# STAGE 2: Minimal Runtime Stage
# ==========================================
FROM python:3.11-slim AS runner

LABEL maintainer="Mahasiswa Kapita Selekta"
LABEL description="FastAPI ML Inference Service with Distributed DB & Keycloak SSO"

WORKDIR /app

# Install only minimal runtime dependencies and curl for Docker healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create a non-privileged user for production container security
RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -m -s /bin/bash appuser

# Copy application source code and pre-trained model artifact
COPY --chown=appuser:appgroup app /app/app
COPY --from=builder --chown=appuser:appgroup /build/model /app/model

# Switch to non-root user
USER appuser

EXPOSE 8000

# Docker Container Healthcheck
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start FastAPI application with Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

