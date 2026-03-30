# Babycat — App Container
# Base: NanoLLM (VILA VLM inference + PyTorch + CUDA)
# Added: nvidia-l4t-gstreamer (nvv4l2decoder, nvvidconv) + gstreamer1.0-plugins-bad
#
# Target: Jetson Orin NX 16GB, JetPack 6.2 (L4T R36.5.x)
# Build:  docker build -f docker/app/Dockerfile -t babycat-app .
# Run:    see compose.yml

FROM dustynv/nano_llm:r36.4.0

# Install GStreamer bad plugins (h264parse, rtph264depay, videorate, ...)
# NVIDIA GStreamer plugins (nvv4l2decoder, nvvidconv, ...) are NOT installed here.
# They are provided at runtime via host bind-mounts (see compose.yml):
#   /usr/lib/aarch64-linux-gnu/gstreamer-1.0  -> GST_PLUGIN_PATH (NVIDIA .so files)
#   /usr/lib/aarch64-linux-gnu/nvidia          -> LD_LIBRARY_PATH (tegra libs)
# This avoids the l4t-core pre-install script that requires /proc/device-tree at build time.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gstreamer1.0-plugins-bad \
        kmod \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies for the application
RUN pip install --no-cache-dir \
    pillow \
    numpy \
    google-auth \
    requests

WORKDIR /app
COPY app/ .

CMD ["python3", "main.py"]
