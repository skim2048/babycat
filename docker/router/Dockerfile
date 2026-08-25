# @claude Babycat — router container (FastAPI, no hardware access).

FROM python:3.11.16-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Seoul

RUN apt-get update && apt-get install -y --no-install-recommends \
        tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "fastapi==0.141.1" "uvicorn[standard]==0.52.3" "pydantic==2.13.4"

WORKDIR /app
COPY router/ .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
