# Backend image for Render (free web service, Docker runtime).
# Render's native Python runtime cannot apt-get install system packages, and local OCR needs the
# Tesseract binary, so the backend deploys from this Dockerfile instead.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # One Tesseract thread: faster per page on a fractional CPU and keeps memory flat
    OMP_THREAD_LIMIT=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# Render injects PORT; default to 8000 for local runs
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
