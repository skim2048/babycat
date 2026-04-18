# @claude Babycat — App container.
# @claude Base: NanoLLM (VILA VLM inference + PyTorch + CUDA).
# @claude Added: gstreamer1.0-plugins-bad. NVIDIA plugins (nvv4l2decoder, nvvidconv, ...)
# @claude are NOT installed here — they are bind-mounted from the host (see compose.yml).
# @claude Target: Jetson Orin NX 16GB, JetPack 6.2 (L4T R36.5.x).
# @claude Build:  docker build -f docker/app/Dockerfile -t babycat-app .
# @claude Run:    see compose.yml

FROM dustynv/nano_llm:r36.4.0

# @claude Install GStreamer bad plugins (h264parse, rtph264depay, videorate, ...).
# @claude NVIDIA GStreamer plugins (nvv4l2decoder, nvvidconv, ...) are provided via host bind-mounts:
# @claude   /usr/lib/aarch64-linux-gnu/gstreamer-1.0 -> GST_PLUGIN_PATH (NVIDIA .so files)
# @claude   /usr/lib/aarch64-linux-gnu/nvidia         -> LD_LIBRARY_PATH (tegra libs)
# @claude This avoids the l4t-core pre-install script that requires /proc/device-tree at build time.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gstreamer1.0-plugins-bad \
        kmod \
    && rm -rf /var/lib/apt/lists/*

# @claude Python dependencies for the application.
RUN pip install --no-cache-dir \
    pillow \
    numpy

WORKDIR /app
COPY app/ .

CMD ["python3", "main.py"]
