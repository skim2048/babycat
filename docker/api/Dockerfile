# Babycat — API Server Container
# REST API + SQLite (embedded)
# TODO: implement in Phase 1

FROM python:3.11-slim

RUN pip install --no-cache-dir fastapi uvicorn

WORKDIR /app
COPY api/ .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
