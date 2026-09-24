#!/bin/bash
# Replay every olive patch step on a clean msm89x7 v7.1.3-r1 tree.
#
#   kernel/patches/apply-all.sh <kernel-tree> <pmaports-patch-dir>
#
# <kernel-tree>         unpacked linux-postmarketos-qcom-msm89x7 v7.1.3-r1
#                       (msm89x7-mainline/linux, tag v7.1.3-r1)
# <pmaports-patch-dir>  the directory holding pmaports' 0001-*.patch,
#                       0002-*.patch and 0003-*.patch for that package
#
# Order: 00, pmaports 0001-0003, then steps 01-10. Finally the shipped config
# is copied in as .config. Each Python step asserts on the text it edits, so a
# wrong or already-patched tree stops the run instead of half-applying.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TREE=$(cd "${1:?usage: apply-all.sh <kernel-tree> <pmaports-patch-dir>}" && pwd)
PMA=$(cd "${2:?usage: apply-all.sh <kernel-tree> <pmaports-patch-dir>}" && pwd)
PY=${PYTHON:-python3}

echo "== 00-olive-display-touch-v2.patch"
patch -d "$TREE" -p1 --forward --no-backup-if-mismatch < "$HERE/00-olive-display-touch-v2.patch"
for n in 0001 0002 0003; do
    p=$(ls "$PMA"/$n-*.patch)
    echo "== pmaports $(basename "$p")"
    patch -d "$TREE" -p1 --forward --no-backup-if-mismatch < "$p"
done
for step in "$HERE"/[0-9][0-9]-*.py; do
    echo "== $(basename "$step")"
    "$PY" "$step" "$TREE"
done
cp "$HERE/../config-7.1.3-msm89x7-olive-r7" "$TREE/.config"
echo "done: build with"
echo "  make -C '$TREE' ARCH=arm64 LLVM=1 olddefconfig"
echo "  make -C '$TREE' ARCH=arm64 LLVM=1 -j\$(nproc) Image.gz modules qcom/sdm439-xiaomi-olive.dtb"
