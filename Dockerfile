# ---------- Base ----------
    FROM python:3.11-slim AS base

    ENV PYTHONUNBUFFERED=1 \
        PYTHONDONTWRITEBYTECODE=1 \
        PIP_NO_CACHE_DIR=1 \
        PIP_DISABLE_PIP_VERSION_CHECK=1
    
    WORKDIR /app
    
    # tools ที่จำเป็นจริง ๆ (เอา curl ไว้ใช้ healthcheck)
    RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl \
     && rm -rf /var/lib/apt/lists/*
    
    # user ปลอดภัย
    RUN groupadd -r appuser && useradd -r -g appuser appuser
    
    # ---------- Production ----------
    FROM base AS prod
    
    # ติดตั้ง deps ของโปรดักชัน
    COPY requirements.txt .
    RUN pip install --no-cache-dir -r requirements.txt
    
    # ✅ คัดลอกทั้งโปรเจกต์ (จะมีทั้ง app/ และ db/)
    COPY . .
    
    # ให้สิทธิ์
    RUN chown -R appuser:appuser /app
    USER appuser
    
    EXPOSE 8000

    
    # รัน uvicorn
    CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]