# ---------- Base ----------
    FROM python:3.11-slim AS base

    ENV PYTHONUNBUFFERED=1 \
        PYTHONDONTWRITEBYTECODE=1 \
        PIP_NO_CACHE_DIR=1 \
        PIP_DISABLE_PIP_VERSION_CHECK=1
    
    WORKDIR /app
    
    # ติดตั้ง system dependencies ที่อาจจำเป็นต่อบาง libs
    RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl \
        && rm -rf /var/lib/apt/lists/*
    
    # สร้าง user ปลอดภัย
    RUN groupadd -r appuser && useradd -r -g appuser appuser
    
    # ---------- Dependencies (Production) ----------
    FROM base AS prod
    COPY requirements.txt .
    RUN pip install --no-cache-dir -r requirements.txt
    
    # Copy source code
    COPY ./app ./app
    
    # เปลี่ยน owner
    RUN chown -R appuser:appuser /app
    USER appuser
    
    EXPOSE 8000
    
    # Healthcheck (ใช้ curl ไม่ต้องพึ่ง requests)
    HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
        CMD curl -f http://localhost:8000/health || exit 1
    
    CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
    
    # ---------- Dependencies (Development) ----------
    FROM base AS dev
    COPY requirements-dev.txt .
    RUN pip install --no-cache-dir -r requirements-dev.txt
    
    COPY ./app ./app
    
    RUN chown -R appuser:appuser /app
    USER appuser
    
    EXPOSE 8000
    
    CMD ["uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"]
    