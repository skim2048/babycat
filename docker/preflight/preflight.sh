#!/bin/sh
# Babycat 사전 검사 — docker compose up 시 analyzer·recorder보다 먼저 실행되어,
# 호스트가 하드웨어 디코더·인코더 경로를 제공하는지 확인한다. 하나라도 실패하면
# 0이 아닌 코드로 종료하고, Compose는 analyzer·recorder를 기동하지 않는다.
# 원인과 조치는 이 컨테이너의 로그(docker compose logs preflight)에 남는다.
#
# 검사 항목은 실제 장애 사례에서 나온 것이다(2026-08-26~27):
#   - JetPack 6.2.2(R36.5)에서 nvv4l2decoder가 하드웨어 경로를 열지 못함
#   - nvidia-l4t-gstreamer 미설치로 nvv4l2decoder 요소가 없음
#   - /tmp/nvscsock(NvSciIPC 소켓) 부재 시 CUDA_GPU_ID 오류로 디코더 실패
#
# 마운트(docker-compose.yml): /etc/nv_tegra_release, /dev → /host/dev, /tmp → /host/tmp,
# 호스트 GStreamer 플러그인과 tegra 라이브러리(recorder와 동일).
set -u

fail=0
ok()   { echo "preflight: [OK]   $1"; }
bad()  { echo "preflight: [FAIL] $1"; echo "               조치: $2"; fail=1; }

# 1. JetPack(L4T) 릴리스 — R36.4.x만 지원
if [ -r /host/nv_tegra_release ]; then
  rel=$(head -1 /host/nv_tegra_release)
  case "$rel" in
    *"R36 (release), REVISION: 4."*) ok "L4T $(echo "$rel" | sed 's/^# //; s/, GCID.*//')" ;;
    *) bad "지원하지 않는 L4T 릴리스: $(echo "$rel" | sed 's/^# //; s/, GCID.*//')" \
           "JetPack 6.2.1(L4T R36.4.x)로 플래시한다. R36.5(JetPack 6.2.2)는 하드웨어 디코더 경로가 열리지 않는다(2026-08-27 확인)" ;;
  esac
else
  bad "/etc/nv_tegra_release를 읽을 수 없다" "Jetson 보드인지, docker-compose.yml의 마운트가 있는지 확인한다"
fi

# 2. 장치 노드
for dev in v4l2-nvdec v4l2-nvenc nvmap nvhost-ctrl-gpu nvhost-gpu; do
  if [ -e "/host/dev/$dev" ]; then ok "/dev/$dev"
  else bad "/dev/$dev 없음" "sudo apt update && sudo apt install nvidia-jetpack 후 재부팅"; fi
done

# 3. NvSciIPC 소켓 — 없으면 Docker가 디렉터리를 만들어 고착될 수 있으므로 종류까지 본다
if [ -S /host/tmp/nvscsock ]; then ok "/tmp/nvscsock (소켓)"
elif [ -d /host/tmp/nvscsock ]; then
  bad "/tmp/nvscsock이 소켓이 아니라 디렉터리다" \
      "docker compose down; sudo rmdir /tmp/nvscsock; sudo systemctl restart nvs-service"
else
  bad "/tmp/nvscsock 없음" "sudo systemctl restart nvs-service (서비스가 없으면 sudo apt update && sudo apt install nvidia-jetpack 후 재부팅)"
fi

# 4. tegra 라이브러리
if [ -e /usr/lib/aarch64-linux-gnu/nvidia/libnvbufsurface.so ]; then ok "tegra 라이브러리(libnvbufsurface.so)"
else bad "/usr/lib/aarch64-linux-gnu/nvidia/libnvbufsurface.so 없음" "sudo apt update && sudo apt install nvidia-jetpack 후 재부팅"; fi

# 5. NVIDIA GStreamer 요소 — 마운트된 호스트 플러그인으로 실제 로드해 본다
for el in nvv4l2decoder nvv4l2h264enc nvvidconv; do
  if gst-inspect-1.0 "$el" >/dev/null 2>&1; then ok "GStreamer 요소 $el"
  else bad "GStreamer 요소 $el 없음" "sudo apt update && sudo apt install nvidia-jetpack 후 docker compose up -d (플래시 기본 구성에는 NVIDIA GStreamer 플러그인이 없다)"; fi
done

if [ "$fail" -ne 0 ]; then
  echo "preflight: 실패 — analyzer·recorder를 기동하지 않는다. 위 조치 후 docker compose up -d 를 다시 실행한다."
  exit 1
fi
echo "preflight: 모든 검사 통과"
exit 0
