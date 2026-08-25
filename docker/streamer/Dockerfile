# @claude Babycat — streamer container (SDD §4.2, §8.2).
# @claude Two processes: the MediaMTX static binary (copied out of the official
# @claude image via a multi-stage build) and the Python companion that owns the
# @claude profile, PTZ, and source activation. The companion is PID 1 and
# @claude supervises MediaMTX as a child. Version bumps = change the tag below.

FROM bluenviron/mediamtx:1.20.1 AS mediamtx

FROM python:3.11.16-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Seoul

RUN apt-get update && apt-get install -y --no-install-recommends \
        tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "fastapi==0.141.1" "uvicorn[standard]==0.52.3"

COPY --from=mediamtx /mediamtx /usr/local/bin/mediamtx

WORKDIR /app
COPY streamer/ .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
