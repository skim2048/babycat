# Babycat — API Server Container
# REST API (FastAPI) + SQLite (embedded)

FROM python:3.11-slim

RUN pip install --no-cache-dir fastapi uvicorn[standard] pydantic

WORKDIR /app
COPY api/ .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
