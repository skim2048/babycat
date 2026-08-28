#!/bin/sh
# Prepare a freshly flashed Jetson board for Babycat. Run once, on the board:
#
#   sudo tools/setup-jetson.sh
#
# Steps, in this order (the order matters: nvidia-jetpack pulls in
# nvidia-container, which removes an already installed docker-ce, so Docker
# must come after JetPack):
#   1. Check the L4T release — only R36.4.x (JetPack 6.2.1) is supported.
#   2. Install the full JetPack component set (nvidia-jetpack): NVIDIA
#      GStreamer plugins, container toolkit, and the rest.
#   3. Install Docker Engine with the Compose plugin, register the nvidia
#      runtime, and add the invoking user to the docker group.
# Every step is skipped when already done, so re-running is safe.
# Device nodes, the NvSciIPC socket, and plugin loading are verified later by
# the preflight service on every `docker compose up`.
set -eu

[ "$(id -u)" -eq 0 ] || { echo "run with sudo: sudo $0" >&2; exit 1; }
TARGET_USER="${SUDO_USER:-$(logname)}"

step() { echo; echo "== $1"; }

# 1. L4T release
step "L4T release"
rel=$(head -1 /etc/nv_tegra_release 2>/dev/null || true)
case "$rel" in
  *"R36 (release), REVISION: 4."*) echo "$rel" ;;
  *) echo "unsupported release: ${rel:-unknown}" >&2
     echo "flash JetPack 6.2.1 (L4T R36.4.x); on 6.2.2 (R36.5) the hardware decoder path does not open" >&2
     exit 1 ;;
esac

# 2. JetPack components
step "JetPack components (nvidia-jetpack)"
if dpkg -s nvidia-jetpack >/dev/null 2>&1; then
  echo "already installed: $(dpkg -s nvidia-jetpack | awk '/^Version/{print $2}')"
else
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y nvidia-jetpack
fi

# 3. Docker Engine
step "Docker Engine"
if ! [ -f /etc/apt/sources.list.d/docker.list ]; then
  apt-get install -y ca-certificates curl
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
fi
if dpkg -s docker-ce >/dev/null 2>&1 && dpkg -s containerd.io >/dev/null 2>&1; then
  echo "already installed: $(docker --version)"
else
  DEBIAN_FRONTEND=noninteractive apt-get install -y \
    docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

# nvidia runtime — nvidia-container-toolkit was installed by nvidia-jetpack
if ! grep -q '"nvidia"' /etc/docker/daemon.json 2>/dev/null; then
  nvidia-ctk runtime configure --runtime=docker
  systemctl restart docker
fi

# docker group
if id -nG "$TARGET_USER" | grep -qw docker; then
  echo "$TARGET_USER is already in the docker group"
else
  usermod -aG docker "$TARGET_USER"
  echo "added $TARGET_USER to the docker group (takes effect after re-login)"
fi

step "done"
echo "reboot now: sudo reboot"
echo "after the reboot, run docker compose up -d in the babycat directory; preflight verifies the remaining conditions."
