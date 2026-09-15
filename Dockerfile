# FastAPI Backend Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install python dependencies first for layer caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Expose backend port
EXPOSE 5000

ENV PORT=5000 \
    PYTHONUNBUFFERED=1

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:5000/health || exit 1

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-5000}"]
