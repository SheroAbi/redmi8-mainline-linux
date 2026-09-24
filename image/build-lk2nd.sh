#!/bin/bash
# Build lk2nd for the Redmi 8: the second-stage bootloader on the boot
# partition. The stock Xiaomi bootloader starts it like a kernel; lk2nd then
# reads /extlinux/extlinux.conf from the disk image on userdata.
#
#   image/build-lk2nd.sh            (image/build-image.sh calls it)
#
# Upstream lk2nd at the commit of 2026-09-20 that the reference phone runs;
# the Redmi 8 (sdm439-xiaomi-olive) is part of its msm8952 target.
#
# Host packages: gcc-arm-none-eabi make python3 python3-libfdt
# device-tree-compiler git
set -euo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
WORK=${WORK:-/var/tmp/redmi8-lk2nd}
OUT=${OUT:-$REPO/dist/image}
LK2ND_REPO=https://github.com/msm8916-mainline/lk2nd
LK2ND_COMMIT=8b46487c4c76776c4f2f61468d44a74c69e6b9ea
TARGET=lk2nd-msm8952

for t in git make python3 dtc arm-none-eabi-gcc; do
	command -v "$t" >/dev/null || { echo "missing host tool: $t" >&2; exit 1; }
done

rm -rf "$WORK/lk2nd"
mkdir -p "$WORK" "$OUT"
git init -q "$WORK/lk2nd"
git -C "$WORK/lk2nd" fetch -q --depth 1 "$LK2ND_REPO" "$LK2ND_COMMIT"
git -C "$WORK/lk2nd" checkout -q FETCH_HEAD

make -C "$WORK/lk2nd" TOOLCHAIN_PREFIX=arm-none-eabi- "$TARGET" -j"$(nproc)"
install -m 644 "$WORK/lk2nd/build-$TARGET/lk2nd.img" "$OUT/lk2nd.img"
ls -l "$OUT/lk2nd.img"
