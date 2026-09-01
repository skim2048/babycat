#!/bin/sh
# Verify that this board and this checkout can run Babycat. Checks only —
# nothing is changed. Run from the cloned repository, as a regular user:
#
#   tools/check-babycat.sh
#
# Exits non-zero when any check fails; each failure prints its fix.
# The host checks come from real failures (2026-08-26..27): a missing
# nvidia-l4t-gstreamer left nvv4l2decoder undefined, a missing NvSciIPC
# socket broke the decoder with CUDA_GPU_ID errors, and JetPack 6.2.2
# (R36.5) cannot open the hardware decoder path at all.
set -u

cd "$(dirname "$0")/.."

FIX_SETUP="run sudo tools/setup-babycat.sh (then reboot if it installed packages)"

fail=0
ok()   { echo "[OK]   $1"; }
bad()  { echo "[FAIL] $1"; echo "       fix: $2"; fail=1; }

echo "== host"

# L4T release — only R36.4.x is supported
rel=$(head -1 /etc/nv_tegra_release 2>/dev/null || true)
case "$rel" in
  *"R36 (release), REVISION: 4."*) ok "L4T $(echo "$rel" | sed 's/^# //; s/, GCID.*//')" ;;
  *) bad "unsupported L4T release: $(echo "$rel" | sed 's/^# //; s/, GCID.*//')" \
         "flash JetPack 6.2.1 (L4T R36.4.x); on R36.5 (JetPack 6.2.2) the hardware decoder path does not open" ;;
esac

# Device nodes
for dev in v4l2-nvdec v4l2-nvenc nvmap nvhost-ctrl-gpu nvhost-gpu; do
  if [ -e "/dev/$dev" ]; then ok "/dev/$dev"
  else bad "/dev/$dev missing" "$FIX_SETUP"; fi
done

# NvSciIPC socket — when missing, Docker creates a directory in its place
# and the daemon can no longer create the socket, so check the type too
if [ -S /tmp/nvscsock ]; then ok "/tmp/nvscsock (socket)"
elif [ -d /tmp/nvscsock ]; then
  bad "/tmp/nvscsock is a directory, not a socket" \
      "docker compose down; sudo rmdir /tmp/nvscsock; sudo systemctl restart nvs-service"
else
  bad "/tmp/nvscsock missing" "sudo systemctl restart nvs-service (if the service does not exist: $FIX_SETUP)"
fi

# tegra libraries
if [ -e /usr/lib/aarch64-linux-gnu/nvidia/libnvbufsurface.so ]; then ok "tegra libraries (libnvbufsurface.so)"
else bad "/usr/lib/aarch64-linux-gnu/nvidia/libnvbufsurface.so missing" "$FIX_SETUP"; fi

# NVIDIA GStreamer elements — the containers mount the host plugin directory,
# so an element missing here is missing inside them too
if command -v gst-inspect-1.0 >/dev/null 2>&1; then
  for el in nvv4l2decoder nvv4l2h264enc nvvidconv; do
    if gst-inspect-1.0 "$el" >/dev/null 2>&1; then ok "GStreamer element $el"
    else bad "GStreamer element $el missing" "$FIX_SETUP (a bare flash ships without the NVIDIA GStreamer plugins)"; fi
  done
else
  bad "gst-inspect-1.0 not found" "$FIX_SETUP"
fi

# Docker access
if docker ps >/dev/null 2>&1; then ok "docker (daemon reachable as $(id -un))"
else bad "docker unreachable (not installed, not running, or $(id -un) not in the docker group)" "$FIX_SETUP, then re-login"; fi

echo "== instance"

# .env and its required values
if [ -f .env ]; then
  ok ".env present"
  for var in HOST_IP DEFAULT_USER DEFAULT_PASS VLM_MODELS; do
    if grep -q "^$var=.\+" .env; then ok ".env $var set"
    else bad ".env $var is empty or missing" "edit .env (see .env.example)"; fi
  done
else
  bad ".env missing" "$FIX_SETUP, or copy and edit .env.example yourself"
fi

# Data directories
missing=""
for d in data/db/router data/db/recorder data/models data/state/analyzer data/state/recorder data/clips data/caddy; do
  [ -d "$d" ] || missing="$missing $d"
done
if [ -z "$missing" ]; then ok "data directories present"
else bad "data directories missing:$missing" "$FIX_SETUP"; fi

echo "== certificate"

# Informational: which CA will sign the server certificate
DEVICE_CA=data/caddy/caddy/pki/authorities/local/root.crt
if [ -f "$DEVICE_CA" ]; then
  echo "signing CA: $(openssl x509 -in "$DEVICE_CA" -noout -subject 2>/dev/null || echo 'unreadable (root-owned; issued at first boot)')"
else
  echo "signing CA: none installed — a development CA will be created at first boot"
  echo "(for a product board, install the Device CA first: see https://github.com/skim2048/babycat-ca)"
fi

echo
if [ "$fail" -ne 0 ]; then
  echo "FAILED — apply the fixes above and run this check again."
  exit 1
fi
echo "all checks passed — start with: docker compose up -d"
exit 0
