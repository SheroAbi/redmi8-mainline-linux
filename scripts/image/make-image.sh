#!/bin/sh
# make-image.sh — run ON a working Redmi 8 as root.
#
# Builds a flashable `userdata` image of the running system: the same boot
# partition layout the initramfs expects (MBR sub-disk, p1 pmOS_boot ext2
# 512 MiB, p2 pmOS_root ext4), the same filesystem UUIDs (extlinux and fstab
# stay valid), but without this phone's secrets:
#
#   removed   Wi-Fi networks and passwords, SSH host keys, every
#             authorized_keys, shell history, keyrings, caches, logs, apt
#             lists, the rescue boot counter
#   reset     user "user" password = 1234 (change it), root password locked,
#             root SSH login key-only
#   added     olive-firstboot.service: new SSH host keys on the first boot
#
# The root filesystem is sized to its content plus headroom; the initramfs
# grows partition and filesystem to the whole userdata partition on the first
# boot. The result is an Android sparse image for `fastboot flash userdata`.
#
#   sh make-image.sh [OUTDIR]        (default /var/tmp/redmi8-image)
#
# EXTRA_EXCLUDES: more tar --exclude patterns, space separated, relative to /
# (for example './home/user/my-build-dir'), for anything else that must not
# end up in a shareable image.
set -eu
OUT=${1:-/var/tmp/redmi8-image}
NAME=redmi8-ubuntu-$(date +%Y%m%d)
ROOT_UUID=$(findmnt -no UUID /)
BOOT_UUID=$(findmnt -no UUID /boot)
DISK=$(findmnt -no SOURCE / | sed 's/p[0-9]*$//')        # /dev/loop0 (sub-disk)
log() { echo "[$(date +%H:%M:%S)] $*"; }

[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
grep -q 'xiaomi,olive' /proc/device-tree/compatible || { echo "not a Redmi 8"; exit 1; }
case "$OUT" in /var/tmp/*) ;; *) echo "OUTDIR must be under /var/tmp (excluded from the copy)"; exit 1 ;; esac
rm -rf "$OUT"
mkdir -p "$OUT/root" "$OUT/boot"

log "copying the root filesystem"
tar -C / --one-file-system --xattrs --xattrs-include='*' --acls --numeric-owner -cpf - \
    --exclude='./var/tmp/*' --exclude='./tmp/*' --exclude='./lost+found/*' \
    --exclude='./var/cache/apt/archives/*.deb' --exclude='./var/cache/apt/archives/partial/*' \
    --exclude='./var/cache/apt/*.bin' --exclude='./var/lib/apt/lists/*' \
    --exclude='./var/log/journal/*' --exclude='./var/log/*.gz' --exclude='./var/log/*.[0-9]' \
    --exclude='./var/crash/*' --exclude='./var/lib/olive/*' --exclude='./var/lib/NetworkManager/*' \
    --exclude='./var/lib/bluetooth/*' --exclude='./var/lib/systemd/random-seed' \
    --exclude='./etc/netplan/90-NM-*' --exclude='./etc/NetworkManager/system-connections/*' \
    --exclude='./etc/ssh/ssh_host_*' \
    --exclude='./root/.ssh/authorized_keys' --exclude='./root/.cache' --exclude='./root/.bash_history' \
    --exclude='./home/user/.ssh/authorized_keys' --exclude='./home/user/.cache' \
    --exclude='./home/user/.bash_history' --exclude='./home/user/.local/share/keyrings' \
    --exclude='./home/user/.local/share/recently-used.xbel' --exclude='./home/user/.local/share/Trash' \
    --exclude='./swapfile' \
    $(for e in ${EXTRA_EXCLUDES:-}; do printf "%s " "--exclude=$e"; done) \
    . | tar -C "$OUT/root" --xattrs --xattrs-include='*' --acls --numeric-owner -xpf -
R=$OUT/root

log "resetting accounts and first-boot state"
HASH=$(openssl passwd -6 1234)
awk -F: -v OFS=: -v h="$HASH" '$1=="user"{$2=h} $1=="root"{$2="!"} {print}' "$R/etc/shadow" > "$R/etc/shadow.new"
cat "$R/etc/shadow.new" > "$R/etc/shadow"; rm "$R/etc/shadow.new"
cat > "$R/etc/ssh/sshd_config.d/00-olive.conf" <<'EOF'
# Redmi 8 image defaults. user/1234 over USB (172.16.43.1) until you change it;
# root only with a key (scripts/install/personalize.py installs one).
PermitRootLogin prohibit-password
PasswordAuthentication yes
PubkeyAuthentication yes
EOF
cat > "$R/etc/systemd/system/olive-firstboot.service" <<'EOF'
[Unit]
Description=Redmi 8: first boot of a fresh image (new SSH host keys)
ConditionPathExists=!/etc/ssh/ssh_host_ed25519_key
Before=ssh.service ssh.socket

[Service]
Type=oneshot
ExecStart=/usr/bin/ssh-keygen -A

[Install]
WantedBy=multi-user.target
EOF
ln -sf /etc/systemd/system/olive-firstboot.service "$R/etc/systemd/system/multi-user.target.wants/olive-firstboot.service"
mkdir -p "$R/var/lib/olive" "$R/var/lib/apt/lists/partial"
echo "$NAME" > "$R/etc/olive-build"

log "copying the boot partition"
for f in extlinux/extlinux.conf extlinux/olive-main.conf extlinux/olive-r6-safe.conf \
         olive-main/vmlinuz olive-main/initramfs olive-main/sdm439-xiaomi-olive.dtb \
         vmlinuz initramfs sdm439-xiaomi-olive.dtb config; do
    install -D -m 0644 "/boot/$f" "$OUT/boot/$f"
done

USED_MB=$(du -sxm "$R" | cut -f1)
FILES=$(find "$R" -xdev | wc -l)
ROOT_MB=$(( (USED_MB * 115 / 100 + 1024 + 63) / 64 * 64 ))
log "root: ${USED_MB} MiB in ${FILES} entries -> filesystem ${ROOT_MB} MiB"

log "creating filesystems"
mke2fs -q -F -t ext2 -b 4096 -L pmOS_boot -U "$BOOT_UUID" -d "$OUT/boot" "$OUT/boot.ext2" 512M
mke2fs -q -F -t ext4 -b 4096 -O ^orphan_file,^metadata_csum_seed -m 1 -N $((FILES * 3 / 2 + 65536)) \
    -L pmOS_root -U "$ROOT_UUID" -d "$R" "$OUT/root.ext4" "${ROOT_MB}M"
e2fsck -fn "$OUT/boot.ext2" >/dev/null
e2fsck -fn "$OUT/root.ext4" >/dev/null
rm -rf "$R" "$OUT/boot"

log "assembling the sub-disk (MBR, same partition starts as $DISK)"
P1_START=2048; P1_SECT=1048576; P2_START=$((P1_START + P1_SECT))
P2_SECT=$((ROOT_MB * 2048))
RAW=$OUT/$NAME.raw
truncate -s $(( (P2_START + P2_SECT) * 512 )) "$RAW"
dd if="$DISK" of="$RAW" bs=512 count=1 conv=notrunc status=none            # MBR incl. disk id
dd if="$OUT/boot.ext2" of="$RAW" bs=1M seek=1 conv=notrunc,sparse status=none
dd if="$OUT/root.ext4" of="$RAW" bs=1M seek=$((P2_START / 2048)) conv=notrunc,sparse status=none
rm -f "$OUT/boot.ext2" "$OUT/root.ext4"
python3 - "$RAW" "$P1_START" "$P1_SECT" "$P2_START" "$P2_SECT" <<'EOF'
import struct, sys
path, s1, n1, s2, n2 = sys.argv[1], *map(int, sys.argv[2:])
with open(path, 'r+b') as f:
    mbr = bytearray(f.read(512))
    assert mbr[510:512] == b'\x55\xaa', 'no MBR on the source disk'
    for idx, (start, count) in enumerate(((s1, n1), (s2, n2))):
        off = 446 + 16 * idx
        assert mbr[off + 4] == 0x83, 'partition %d is not Linux' % (idx + 1)
        assert struct.unpack_from('<I', mbr, off + 8)[0] == start, 'partition %d start moved' % (idx + 1)
        struct.pack_into('<I', mbr, off + 12, count)
    mbr[446 + 32:510] = bytes(510 - 446 - 32)          # no third/fourth entry
    f.seek(0); f.write(mbr)
EOF

log "writing the Android sparse image"
python3 - "$RAW" "$OUT/$NAME-userdata.img" <<'EOF'
# Android sparse v1.0: RAW chunks for data, FILL(0) for zero runs. FILL (not
# DONT_CARE) so the flashed partition matches the image byte for byte.
import struct, sys
src, dst = sys.argv[1], sys.argv[2]
BS = 4096
ZERO = bytes(BS)
chunks = []                     # (kind, blocks, payload-offset-in-src)
with open(src, 'rb') as f:
    f.seek(0, 2); size = f.tell(); f.seek(0)
    assert size % BS == 0
    total = size // BS
    kind = None; start = 0; n = 0
    for i in range(total):
        blk = f.read(BS)
        k = 'Z' if blk == ZERO else 'R'
        if k != kind:
            if kind: chunks.append((kind, n, start))
            kind, start, n = k, i, 0
        n += 1
    chunks.append((kind, n, start))
with open(src, 'rb') as f, open(dst, 'wb') as out:
    out.write(struct.pack('<IHHHHIIII', 0xed26ff3a, 1, 0, 28, 12, BS, total, len(chunks), 0))
    for kind, n, start in chunks:
        if kind == 'R':
            out.write(struct.pack('<HHII', 0xCAC1, 0, n, 12 + n * BS))
            f.seek(start * BS)
            left = n * BS
            while left:
                buf = f.read(min(left, 8 << 20)); out.write(buf); left -= len(buf)
        else:
            out.write(struct.pack('<HHII', 0xCAC2, 0, n, 16))
            out.write(struct.pack('<I', 0))
print('sparse: %d blocks, %d chunks' % (total, len(chunks)))
EOF
rm -f "$RAW"

cd "$OUT"
sha256sum "$NAME-userdata.img" > "$NAME-userdata.img.sha256"
cat > "$NAME.manifest" <<EOF
name=$NAME
kernel=$(uname -r)
build_from=$(cat /etc/olive-build)
root_uuid=$ROOT_UUID
boot_uuid=$BOOT_UUID
root_fs_mib=$ROOT_MB
root_used_mib=$USED_MB
entries=$FILES
default_login=user / 1234 (root locked, root ssh key-only)
EOF
ls -la "$OUT"
log "done"
