# @claude Babycat — analyzer container.
# @claude Base: NanoLLM (VILA VLM inference + PyTorch + CUDA), pinned to the
# @claude L4T R36.4 build. NVIDIA plugins (nvv4l2decoder, nvvidconv, ...) are
# @claude NOT installed here — they are bind-mounted from the host (see
# @claude docker-compose.yml). Target: Jetson Orin, JetPack 6.2.x (L4T R36.4.x).
# @claude Build:  docker compose build analyzer

FROM dustynv/nano_llm:r36.4.0

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Seoul

# @claude gstreamer1.0-plugins-bad supplies h264parse; rtph264depay (-good) and
# @claude videorate (-base) come with the base image.
# @claude NVIDIA GStreamer plugins (nvv4l2decoder, nvvidconv, ...) are provided via host bind-mounts:
# @claude   /usr/lib/aarch64-linux-gnu/gstreamer-1.0 -> GST_PLUGIN_PATH (NVIDIA .so files)
# @claude   /usr/lib/aarch64-linux-gnu/nvidia         -> LD_LIBRARY_PATH (tegra libs)
# @claude This avoids the l4t-core pre-install script that requires /proc/device-tree at build time.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tzdata \
        gstreamer1.0-plugins-bad \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# @claude pillow and numpy come with the base image; nothing is added.

# @claude Patch the clip_trt package (from the NanoLLM base image). Its init_trt()
# @claude builds the engine file path with os.path.expanduser() but calls
# @claude os.makedirs() on the raw "~/.cache/clip_trt" string, creating a literal
# @claude "~" directory in the container CWD (/app). Expand the
# @claude tilde so the cache dir resolves to /root/.cache/clip_trt as intended.
# @claude The grep guards fail the build if the base image no longer matches.
RUN set -eu; \
    for f in vision text timm2trt; do \
        p="/opt/clip_trt/clip_trt/$f.py"; \
        grep -q 'os.makedirs(trt_cache,' "$p"; \
        sed -i 's/os\.makedirs(trt_cache,/os.makedirs(os.path.expanduser(trt_cache),/' "$p"; \
        grep -q 'os.makedirs(os.path.expanduser(trt_cache),' "$p"; \
    done; \
    rm -rf /opt/clip_trt/clip_trt/__pycache__

WORKDIR /app
COPY analyzer/ .

# @claude Create the TensorRT engine cache dir at runtime. The base image symlinks
# @claude /root/.cache/clip_trt -> /data/models/clip, and /data is a host bind-mount,
# @claude so the dir must be created after mounts are applied (a build-time RUN would
# @claude be shadowed by the bind-mount). Without it torch.save() of the compiled
# @claude engine fails and the engine is never cached. 'exec' keeps python3 as PID 1
# @claude so it receives SIGTERM directly for graceful pipeline shutdown.
CMD ["sh", "-c", "mkdir -p /data/models/clip && exec python3 main.py"]
