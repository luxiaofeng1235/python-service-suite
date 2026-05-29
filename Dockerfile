# ==================== Build Stage ====================
FROM python:3.12-slim AS builder

WORKDIR /app

# Install system deps needed for pip install
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ==================== Runtime Stage ====================
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install runtime system deps (mysql client for production)
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-mysql-client \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy pip packages from builder
COPY --from=builder /root/.local /root/.local

# Ensure local bin is in PATH
ENV PATH=/root/.local/bin:$PATH

# Copy project
COPY . .

# Create persistent directories
RUN mkdir -p logs uploads

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# Start
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
