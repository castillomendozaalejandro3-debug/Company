FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    libopencv-dev \
    protobuf-compiler \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements primero para aprovechar cache
COPY ai_engine/requirements.txt ./requirements.txt

# Instalar dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fuente
COPY ai_engine/ ./ai_engine/
COPY logs/ ./logs/

# Crear directorio para archivos temporales
RUN mkdir -p /app/temp

# Variables de entorno
ENV PYTHONPATH=/app
ENV LOG_LEVEL=INFO

EXPOSE 8000

CMD ["uvicorn", "ai_engine.main:app", "--host", "0.0.0.0", "--port", "8000"]
