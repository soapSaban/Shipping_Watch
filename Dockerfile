FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install basic compiler toolchain needed for faiss-cpu and numpy C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    dos2unix \
    && rm -rf /var/lib/apt/lists/*

# Install CPU-only torch first for fast build and lightweight image (~150MB vs 1.5GB)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install remaining application dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Fix potential Windows CRLF issues and make entrypoint executable
RUN dos2unix entrypoint.sh && chmod +x entrypoint.sh

# Ensure output directory exists
RUN mkdir -p output

EXPOSE 5000

ENTRYPOINT ["./entrypoint.sh"]
