# @claude Babycat — recorder container.
# @claude GStreamer (NVENC segment recorder) + ffmpeg (copy-concat / fallback) +
# @claude FastAPI (clips, history, status). NVIDIA GStreamer plugins
# @claude (nvv4l2decoder, nvv4l2h264enc, nvvidconv) are NOT installed here —
# @claude they are bind-mounted from the host (see docker-compose.yml).
# @claude ubuntu:22.04 matches the L4T R36 userspace (glibc) that those plugins
# @claude link against. Build: docker compose build recorder

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Seoul

RUN apt-get update && apt-get install -y --no-install-recommends \
        tzdata \
        python3 \
        python3-pip \
        python3-gi \
        gir1.2-gst-plugins-base-1.0 \
        gstreamer1.0-tools \
        gstreamer1.0-plugins-base \
        gstreamer1.0-plugins-good \
        gstreamer1.0-plugins-bad \
        ffmpeg \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir "fastapi==0.141.1" "uvicorn[standard]==0.52.3" "pydantic==2.13.4"

WORKDIR /app
COPY recorder/ .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
