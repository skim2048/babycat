#!/bin/sh
# Root CA 인증서를 mewly 앱의 리소스로 복사한다.
#
# 사용법: tools/cp-rootcrt.sh <mewly 저장소 경로>
#   예)   tools/cp-rootcrt.sh ~/projects/mewly
#
# 원본: $ROOT_DIR/root.crt (기본 ~/.babycat-ca, provision-device.sh init이 생성)
# 대상: <mewly>/android/app/src/main/res/raw/babycat_ca.crt
# 복사 후 mewly 앱을 다시 빌드해야 적용된다.
set -eu

MEWLY="${1:?mewly 저장소 경로가 필요하다 (예: ~/projects/mewly)}"
ROOT_DIR="${ROOT_DIR:-$HOME/.babycat-ca}"
SRC="$ROOT_DIR/root.crt"
DEST_DIR="$MEWLY/android/app/src/main/res/raw"
DEST="$DEST_DIR/babycat_ca.crt"

[ -f "$SRC" ] || { echo "Root CA 인증서가 없다: $SRC (먼저 tools/provision-device.sh init)" >&2; exit 1; }
[ -d "$DEST_DIR" ] || { echo "mewly의 리소스 디렉터리가 없다: $DEST_DIR" >&2; exit 1; }

cp "$SRC" "$DEST"
echo "복사했다: $DEST"
openssl x509 -in "$DEST" -noout -subject -enddate
