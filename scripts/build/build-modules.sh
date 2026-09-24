#!/bin/bash
# Build the three out-of-tree drivers (backlight, touch, battery/charger).
#
#   scripts/build/build-modules.sh <kernel-tree>
#
# <kernel-tree> is any 7.1.3 msm89x7 tree: the modules only need headers
# and a configured build, so an unpatched worktree prepared with our config
# works (that is how the running modules were built). Output: kernel/modules/*.ko
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
K=${1:?usage: build-modules.sh <kernel-tree>}
CONFIG=$HERE/kernel/config-7.1.3-msm89x7-olive-r7
grep -q 'CONFIG_MODULE_SIG_FORCE=y' "$CONFIG" && { echo "module signatures enforced"; exit 1; }
cp "$CONFIG" "$K/.config"
make -C "$K" ARCH=arm64 LLVM=1 LOCALVERSION= -s olddefconfig
make -C "$K" ARCH=arm64 LLVM=1 LOCALVERSION= -s modules_prepare
release=$(make -C "$K" -s LOCALVERSION= kernelrelease)
[ "$release" = 7.1.3-msm89x7-olive-r7 ] || { echo "tree says $release, expected 7.1.3-msm89x7-olive-r7"; exit 1; }
make -C "$HERE/kernel/modules" KDIR="$K"
for m in "$HERE"/kernel/modules/*.ko; do modinfo "$m" | grep -E '^(filename|vermagic)'; done
