FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY scam_shield ./scam_shield

# Run as a non-root user.
RUN useradd --create-home --uid 10001 app
USER app

# Cloud Run sets $PORT.
CMD ["sh", "-c", "exec uvicorn scam_shield.api:app --host 0.0.0.0 --port ${PORT:-8080}"]
