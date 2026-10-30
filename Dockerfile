# Backend Loopa untuk Railway (CPU). Bobot model harus ada di backend/models/best.pt sebelum build.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 libxcb1 libsm6 libxext6 libxrender1 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-ml.txt ./
# torch versi CPU supaya image jauh lebih kecil daripada build CUDA default
RUN pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && pip install -r requirements-ml.txt

COPY app ./app
COPY models ./models

ENV INFERENCE_BACKEND=yolo \
    MODEL_PATH=models/best.pt \
    YOLO_DEVICE=cpu \
    YOLO_IMGSZ=320

# State sesi ada di memori proses: wajib 1 worker.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
