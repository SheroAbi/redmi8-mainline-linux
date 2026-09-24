#!/usr/bin/env python3
"""Flash Ubuntu onto a Redmi 8 (olive) from Windows or Linux.

    python scripts/flash/flash.py                 # checks only, writes nothing
    python scripts/flash/flash.py --flash         # userdata + boot (lk2nd)
    python scripts/flash/flash.py --flash --reboot

The phone must be in the STOCK fastboot mode (power off, then hold
Volume-Down + Power) with an unlocked bootloader. What gets written:

    userdata  dist/redmi8-ubuntu-<date>-userdata.img   (Android sparse)
    boot      dist/lk2nd-olive-20260920.img             (lk2nd, boots extlinux)

!! userdata is the whole Android data partition: everything on it is gone.
   Android itself (system, vendor, modem, persist) is not touched, and the
   stock boot image can be flashed back to return to Android.

Before anything is written the script checks: the image checksum and its
sparse structure, that the device says product=olive, unlocked=yes and is the
stock bootloader (kernel=lk), the battery, and that both images fit their
partitions. It never reboots after a failed write.
"""
import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / 'dist'
LK2ND = DIST / 'lk2nd-olive-20260920.img'
LK2ND_SHA256 = '3c718fd12d74483e8b13b949d59fddad7fd7b582e26b9d0ab7ec7d79ecd7b501'


def find_fastboot(given):
    candidates = [given] if given else []
    candidates += [shutil.which('fastboot')]
    for c in candidates:
        if c and Path(c).is_file():
            return c
    raise SystemExit('fastboot not found: install Android platform-tools or pass --fastboot')


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(8 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def sparse_size(path):
    """Expanded size; rejects truncation and unknown chunk types."""
    with path.open('rb') as f:
        magic, major, _minor, fh, ch, bs, blocks, chunks, _crc = struct.unpack('<I4H4I', f.read(28))
        if magic != 0xed26ff3a or major != 1:
            raise SystemExit(f'{path.name} is not an Android sparse image')
        f.seek(fh)
        length, count = path.stat().st_size, 0
        for i in range(chunks):
            kind, _r, n, size = struct.unpack('<2H2I', f.read(ch)[:12])
            payload = {0xcac1: n * bs, 0xcac2: 4, 0xcac3: 0, 0xcac4: 4}.get(kind)
            if payload is None or size != ch + payload:
                raise SystemExit(f'{path.name}: bad chunk {i}')
            count += n
            f.seek(payload, 1)
        if count != blocks or f.tell() != length:
            raise SystemExit(f'{path.name}: truncated or inconsistent')
        return blocks * bs


def latest_image():
    images = sorted(DIST.glob('redmi8-ubuntu-*-userdata.img'))
    if not images:
        raise SystemExit(f'no redmi8-ubuntu-*-userdata.img in {DIST}')
    return images[-1]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--image', type=Path, help='userdata image (default: newest in dist/)')
    p.add_argument('--fastboot', help='path to fastboot')
    p.add_argument('--serial', help='fastboot serial, if more than one device is attached')
    p.add_argument('--flash', action='store_true', help='actually write (default: checks only)')
    p.add_argument('--reboot', action='store_true', help='reboot after a successful flash')
    args = p.parse_args()

    fastboot = find_fastboot(args.fastboot)
    image = args.image or latest_image()
    base = [fastboot] + (['-s', args.serial] if args.serial else [])

    print(f'image   {image}')
    sums = image.with_name(image.name + '.sha256')
    if sums.is_file():
        expected = sums.read_text().split()[0]
        if sha256(image) != expected:
            raise SystemExit('image checksum MISMATCH - download/copy it again')
        print('        checksum ok')
    expanded = sparse_size(image)
    print(f'        {expanded / 2**30:.2f} GiB expanded')
    if sha256(LK2ND) != LK2ND_SHA256:
        raise SystemExit(f'{LK2ND.name}: checksum mismatch')
    print(f'boot    {LK2ND.name} ok')

    def getvar(name):
        try:
            r = subprocess.run(base + ['getvar', name], capture_output=True, timeout=15)
        except subprocess.TimeoutExpired:
            raise SystemExit('no phone in fastboot mode (power off, then hold Volume-Down + Power, '
                             'cable in)') from None
        text = (r.stdout + r.stderr).decode(errors='replace')
        m = re.search(r'^(?:\(bootloader\) )?' + re.escape(name) + r':\s*(.+)$', text, re.M)
        if not m:
            raise SystemExit(f'fastboot getvar {name} failed - is the phone in fastboot mode?\n{text.strip()}')
        return m.group(1).strip()

    v = {k: getvar(k) for k in ('product', 'unlocked', 'kernel', 'battery-voltage',
                                'partition-size:boot', 'partition-size:userdata')}
    print('device  ' + ', '.join(f'{k}={v[k]}' for k in v))
    if v['product'] != 'olive':
        raise SystemExit('this is not a Redmi 8 (olive)')
    if v['unlocked'] != 'yes':
        raise SystemExit('bootloader is locked')
    if v['kernel'] != 'lk':
        raise SystemExit('not the stock bootloader (lk2nd answers too) - power off, '
                         'then hold Volume-Down + Power')
    mv = int(v['battery-voltage'])
    mv = mv // 1000 if mv > 100000 else mv
    if mv < 3700:
        raise SystemExit(f'battery at {mv} mV - charge to at least 3.7 V first')
    if expanded > int(v['partition-size:userdata'], 16):
        raise SystemExit('image larger than userdata')
    if LK2ND.stat().st_size > int(v['partition-size:boot'], 16):
        raise SystemExit('lk2nd larger than boot')
    print('checks  passed')
    if not args.flash:
        print('\nnothing written. Run again with --flash to install.')
        return 0

    for partition, path in (('userdata', image), ('boot', LK2ND)):
        print(f'\n== flashing {partition}', flush=True)
        # -S 256M: the stock bootloader's download buffer; fastboot re-sparses.
        if subprocess.call(base + ['-S', '256M', 'flash', partition, str(path)]) != 0:
            raise SystemExit(f'flashing {partition} FAILED - the phone stays in fastboot, '
                             'nothing was rebooted. Run the command again.')
    print('\nflash complete.')
    if args.reboot:
        subprocess.call(base + ['reboot'])
        print('rebooting: first boot takes about a minute (the root filesystem grows '
              'to the whole partition), then GNOME comes up.')
    else:
        print('reboot with:  fastboot reboot')
    return 0


if __name__ == '__main__':
    sys.exit(main())
