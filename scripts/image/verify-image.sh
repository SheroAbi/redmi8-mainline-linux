#!/bin/sh
# verify-image.sh IMAGE — check a redmi8-ubuntu-*-userdata.img without
# mounting it (no loop device: its filesystems carry the same UUIDs as a
# running Redmi 8, and a second device with those UUIDs can make systemd
# unmount the live root). Runs anywhere with python3 and e2fsprogs.
set -eu
IMG=$1
T=$(mktemp -d /var/tmp/verify.XXXXXX)
trap 'rm -rf "$T"' EXIT
python3 - "$IMG" "$T" <<'EOF'
# Expand the sparse image, then cut out the two partitions named in its MBR.
import struct, sys
src, out = sys.argv[1], sys.argv[2]
with open(src, 'rb') as f, open(out + '/disk.raw', 'wb') as d:
    magic, _maj, _min, fh, ch, bs, blocks, chunks, _ = struct.unpack('<I4H4I', f.read(28))
    assert magic == 0xed26ff3a
    f.seek(fh)
    for _ in range(chunks):
        kind, _r, n, size = struct.unpack('<2H2I', f.read(ch)[:12])
        if kind == 0xCAC1:
            left = n * bs
            while left:
                buf = f.read(min(left, 8 << 20)); d.write(buf); left -= len(buf)
        elif kind == 0xCAC2:
            fill = f.read(4)
            if fill == bytes(4):
                d.seek(n * bs, 1)
            else:
                d.write(fill * (n * bs // 4))
        elif kind == 0xCAC3:
            d.seek(n * bs, 1)
        else:
            f.seek(size - ch, 1)
    d.truncate(blocks * bs)
with open(out + '/disk.raw', 'rb') as d:
    mbr = d.read(512)
    assert mbr[510:] == b'\x55\xaa', 'no MBR'
    for i, name in ((0, 'boot'), (1, 'root')):
        start, count = struct.unpack_from('<II', mbr, 446 + 16 * i + 8)
        print(f'p{i + 1} {name}: start {start} sectors {count}')
        with open(f'{out}/{name}.fs', 'wb') as p:
            d.seek(start * 512); left = count * 512
            while left:
                buf = d.read(min(left, 8 << 20)); p.write(buf); left -= len(buf)
EOF
rm "$T/disk.raw"
fail=0
check() { if eval "$2"; then echo "ok    $1"; else echo "FAIL  $1"; fail=1; fi; }
check "boot filesystem clean" 'e2fsck -fn "$T/boot.fs" >/dev/null 2>&1'
check "root filesystem clean" 'e2fsck -fn "$T/root.fs" >/dev/null 2>&1'
dbg() { debugfs -R "$2" "$T/$1.fs" 2>/dev/null; }
check "boot label/uuid" 'dumpe2fs -h "$T/boot.fs" 2>/dev/null | grep -q "volume name:.*pmOS_boot"'
check "root label/uuid" 'dumpe2fs -h "$T/root.fs" 2>/dev/null | grep -q "volume name:.*pmOS_root"'
for f in extlinux/extlinux.conf olive-main/vmlinuz olive-main/initramfs olive-main/sdm439-xiaomi-olive.dtb; do
    check "boot has /$f" 'dbg boot "stat /$f" | grep -q "Size:"'
done
check "no SSH host keys"          '! dbg root "ls /etc/ssh" | grep -q ssh_host_'
check "no root authorized_keys"   '! dbg root "ls /root/.ssh" | grep -q authorized_keys'
check "no user authorized_keys"   '! dbg root "ls /home/user/.ssh" | grep -q authorized_keys'
check "no Wi-Fi profiles"         '! dbg root "ls /etc/netplan" | grep -q 90-NM'
check "no wpa_supplicant PSK"     '! dbg root "cat /etc/wpa_supplicant/wpa_supplicant-wlan0.conf" | grep -q psk'
# Only a link to msm-firmware-loader (this phone's persist) may stand there.
check "no static Wi-Fi NV"        '! dbg root "stat /lib/firmware/postmarketos/wlan/prima/WCNSS_qcom_wlan_nv.bin" | grep -q "Type: regular" && ! dbg root "stat /lib/firmware/wlan/prima/WCNSS_qcom_wlan_nv.bin" | grep -q "Type: regular"'
check "root password locked"      'dbg root "cat /etc/shadow" | grep -q "^root:!:"'
check "user password set"         'dbg root "cat /etc/shadow" | grep -q "^user:[$]6[$]"'
check "firstboot unit enabled"    'dbg root "ls /etc/systemd/system/multi-user.target.wants" | grep -q olive-firstboot'
check "sshd root key-only"        'dbg root "cat /etc/ssh/sshd_config.d/00-olive.conf" | grep -q prohibit-password'
check "kernel modules present"    'dbg root "ls /usr/lib/modules/7.1.3-msm89x7-olive-r7/extra" | grep -q olive-power'
check "GPU zap firmware present"  'dbg root "ls /usr/lib/firmware/qcom/sdm439/xiaomi/olive" | grep -q a506_zap.mdt'
exit $fail
