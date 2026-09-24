#!/bin/bash
# Build the Redmi 8 kernel, its modules and the three out-of-tree drivers.
#
#   scripts/build/build-kernel.sh
#
# Clones msm89x7-mainline/linux (tag v7.1.3-r1) into $WORK/linux, applies
# kernel/patches/ (apply-all.sh), builds with clang, and stages the result in
# $WORK/kernel for image/build-image.sh:
#   vmlinuz                                   Image.gz
#   config                                    the .config
#   modules/lib/modules/7.1.3-msm89x7-olive-r7/  in-tree modules + extra/*.ko
#
# WORK defaults to ~/redmi8-build (on a Linux filesystem; WSL works).
# Host packages: git make clang lld llvm bc bison flex libssl-dev libelf-dev
# python3 zstd
set -euo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
WORK=${WORK:-$HOME/redmi8-build}
KREL=7.1.3-msm89x7-olive-r7
SRC=$WORK/linux
OUT=$WORK/kernel
MAKE=(make -C "$SRC" ARCH=arm64 LLVM=1 LOCALVERSION=)

for t in git make clang ld.lld bc bison flex python3 zstd; do
	command -v "$t" >/dev/null || { echo "missing host tool: $t" >&2; exit 1; }
done
mkdir -p "$WORK"
if [ ! -f "$SRC/.olive-patched" ]; then
	rm -rf "$SRC"
	git clone --depth 1 --branch v7.1.3-r1 https://github.com/msm89x7-mainline/linux "$SRC"
	"$REPO/kernel/patches/apply-all.sh" "$SRC"
	touch "$SRC/.olive-patched"
fi

echo "=== kernel ==="
cp "$REPO/kernel/config-$KREL" "$SRC/.config"
"${MAKE[@]}" olddefconfig
release=$("${MAKE[@]}" -s kernelrelease)
[ "$release" = "$KREL" ] || { echo "tree says $release, expected $KREL" >&2; exit 1; }
"${MAKE[@]}" -j"$(nproc)" Image.gz modules

echo "=== stage ==="
rm -rf "$OUT"
mkdir -p "$OUT/modules"
"${MAKE[@]}" INSTALL_MOD_STRIP=1 INSTALL_MOD_PATH="$OUT/modules" modules_install
rm -f "$OUT/modules/lib/modules/$KREL/build" "$OUT/modules/lib/modules/$KREL/source"
cp "$SRC/arch/arm64/boot/Image.gz" "$OUT/vmlinuz"
cp "$SRC/.config" "$OUT/config"

echo "=== out-of-tree drivers ==="
make -C "$REPO/kernel/modules" KDIR="$SRC"
install -d "$OUT/modules/lib/modules/$KREL/extra"
install -m 644 "$REPO"/kernel/modules/*.ko "$OUT/modules/lib/modules/$KREL/extra/"
make -C "$REPO/kernel/modules" KDIR="$SRC" clean >/dev/null

ls -l "$OUT/vmlinuz"
echo "modules: $(find "$OUT/modules" -name '*.ko*' | wc -l)"
echo "KERNEL_OK $OUT"
