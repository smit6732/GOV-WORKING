# Model 2 wiring only — this Dockerfile did not exist in the vendored
# ANPR_Standalone microservice. It does not touch any detection/tracking
# code; it only builds a container to run the service as-is.
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# CPU-only torch/torchvision, installed explicitly BEFORE the rest of
# requirements.txt — pip's default index resolves to CUDA wheels (several
# GB of unused packages) unless pointed at the CPU wheel index.
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

# Bake PaddleOCR's model download into the image so the container needs no
# internet access at runtime (instantiating PlateRecognizer() once triggers
# the download-and-cache).
RUN python -c "from anpr.plate_recognizer import PlateRecognizer; PlateRecognizer()"

EXPOSE 8090

CMD ["uvicorn", "service.api:app", "--host", "0.0.0.0", "--port", "8090"]
