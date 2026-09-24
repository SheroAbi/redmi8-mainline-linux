#!/bin/bash
# Replay every olive patch step on a clean msm89x7 v7.1.3-r1 tree.
#
#   kernel/patches/apply-all.sh <kernel-tree>
#
# <kernel-tree> is msm89x7-mainline/linux, tag v7.1.3-r1, e.g.
#   git clone --depth 1 --branch v7.1.3-r1 https://github.com/msm89x7-mainline/linux
#
# Order: 00, 0001, then steps 01-10; finally the shipped config becomes
# .config. Each Python step asserts on the text it edits, so a wrong or
# already-patched tree stops the run instead of half-applying.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TREE=$(cd "${1:?usage: apply-all.sh <kernel-tree>}" && pwd)
PY=${PYTHON:-python3}

for p in 00-olive-display-touch-v2.patch 0001-soc-qcom-ubwc-add-sdm439.patch; do
    echo "== $p"
    patch -d "$TREE" -p1 --forward --no-backup-if-mismatch < "$HERE/$p"
done
# Step 03 edits .config through scripts/config, so one has to exist.
cp "$HERE/../config-7.1.3-msm89x7-olive-r7" "$TREE/.config"
for step in "$HERE"/[0-9][0-9]-*.py; do
    echo "== $(basename "$step")"
    "$PY" "$step" "$TREE"
done
cp "$HERE/../config-7.1.3-msm89x7-olive-r7" "$TREE/.config"
echo "patched: $TREE"
