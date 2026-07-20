# @claude Babycat — Gateway container.
# @claude REST API (FastAPI) + SQLite (embedded).

FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Seoul

RUN apt-get update && apt-get install -y --no-install-recommends \
        tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir fastapi uvicorn[standard] pydantic

WORKDIR /app
COPY gateway/ .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
