#!/bin/sh
# Babycat preflight — runs before analyzer and recorder on every
# `docker compose up` and verifies that the host provides the hardware
# decoder/encoder path. If any check fails it exits non-zero and Compose
# does not start analyzer and recorder; the cause and the fix are in this
# container's log (docker compose logs preflight).
#
# The checks come from real failures (2026-08-26..27):
#   - JetPack 6.2.2 (R36.5): nvv4l2decoder cannot open the hardware path
#   - nvidia-l4t-gstreamer missing: the nvv4l2decoder element does not exist
#   - /tmp/nvscsock (NvSciIPC socket) missing: decoder fails with CUDA_GPU_ID
#
# Mounts (docker-compose.yml): /etc/nv_tegra_release, /dev -> /host/dev,
# /tmp -> /host/tmp, and the host GStreamer plugins and tegra libraries
# (same as recorder).
set -u

FIX_JETPACK="sudo apt update && sudo apt install nvidia-jetpack, then reboot (or run tools/setup-jetson.sh)"

fail=0
ok()   { echo "preflight: [OK]   $1"; }
bad()  { echo "preflight: [FAIL] $1"; echo "               fix: $2"; fail=1; }

# 1. L4T release — only R36.4.x is supported
if [ -r /host/nv_tegra_release ]; then
  rel=$(head -1 /host/nv_tegra_release)
  case "$rel" in
    *"R36 (release), REVISION: 4."*) ok "L4T $(echo "$rel" | sed 's/^# //; s/, GCID.*//')" ;;
    *) bad "unsupported L4T release: $(echo "$rel" | sed 's/^# //; s/, GCID.*//')" \
           "flash JetPack 6.2.1 (L4T R36.4.x); on R36.5 (JetPack 6.2.2) the hardware decoder path does not open (confirmed 2026-08-27)" ;;
  esac
else
  bad "cannot read /etc/nv_tegra_release" "check that this is a Jetson board and that docker-compose.yml mounts the file"
fi

# 2. Device nodes
for dev in v4l2-nvdec v4l2-nvenc nvmap nvhost-ctrl-gpu nvhost-gpu; do
  if [ -e "/host/dev/$dev" ]; then ok "/dev/$dev"
  else bad "/dev/$dev missing" "$FIX_JETPACK"; fi
done

# 3. NvSciIPC socket — when missing, Docker creates a directory in its place
#    and the daemon can no longer create the socket, so check the type too
if [ -S /host/tmp/nvscsock ]; then ok "/tmp/nvscsock (socket)"
elif [ -d /host/tmp/nvscsock ]; then
  bad "/tmp/nvscsock is a directory, not a socket" \
      "docker compose down; sudo rmdir /tmp/nvscsock; sudo systemctl restart nvs-service"
else
  bad "/tmp/nvscsock missing" "sudo systemctl restart nvs-service (if the service does not exist: $FIX_JETPACK)"
fi

# 4. tegra libraries
if [ -e /usr/lib/aarch64-linux-gnu/nvidia/libnvbufsurface.so ]; then ok "tegra libraries (libnvbufsurface.so)"
else bad "/usr/lib/aarch64-linux-gnu/nvidia/libnvbufsurface.so missing" "$FIX_JETPACK"; fi

# 5. NVIDIA GStreamer elements — actually load them from the mounted host plugins
for el in nvv4l2decoder nvv4l2h264enc nvvidconv; do
  if gst-inspect-1.0 "$el" >/dev/null 2>&1; then ok "GStreamer element $el"
  else bad "GStreamer element $el missing" "$FIX_JETPACK (a bare flash ships without the NVIDIA GStreamer plugins)"; fi
done

if [ "$fail" -ne 0 ]; then
  echo "preflight: FAILED — analyzer and recorder will not start. Apply the fixes above and run docker compose up -d again."
  exit 1
fi
echo "preflight: all checks passed"
exit 0
