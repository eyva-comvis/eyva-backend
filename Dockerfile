# syntax=docker/dockerfile:1
# Backend Eyva untuk Railway/Docker.
# Default: build ringan untuk INFERENCE_BACKEND=remote (tanpa PyTorch/OpenCV).
# Untuk mode YOLO lokal:
#   docker build --build-arg INSTALL_ML=true -t eyva-backend .

FROM python:3.12-slim

ARG INSTALL_ML=false

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt requirements-ml.txt ./

# Install dependensi dasar (FastAPI, uvicorn, httpx, supabase, dll.)
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$INSTALL_ML" = "true" ]; then \
        apt-get update && apt-get install -y --no-install-recommends \
            libglib2.0-0 libgl1 libxcb1 libsm6 libxext6 libxrender1 \
            && rm -rf /var/lib/apt/lists/* \
        && pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu \
        && pip install --no-cache-dir -r requirements-ml.txt; \
    fi

COPY app ./app
COPY models ./models

ENV INFERENCE_BACKEND=remote \
    MODEL_API_URL=https://model-production-eyva.up.railway.app \
    MODEL_API_TIMEOUT=10.0 \
    MODEL_PATH=models/best.pt \
    YOLO_DEVICE=cpu \
    YOLO_IMGSZ=320

# State sesi ada di memori proses: wajib 1 worker.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
