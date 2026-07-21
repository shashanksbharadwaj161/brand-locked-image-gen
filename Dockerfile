# Single-image deploy: FastAPI serves both the API and the static frontend.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# App code + frontend (main.py resolves ../frontend relative to itself).
COPY backend ./backend
COPY frontend ./frontend

WORKDIR /app/backend

# Railway/Render/Fly inject $PORT; default to 8000 for local `docker run`.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
