# Installing

## What has to be true first

1. **Bootloader unlocked** (Xiaomi Mi Unlock; `fastboot getvar unlocked` → `yes`).
2. **Android platform-tools** on the PC (`fastboot` on the `PATH`, or pass
   `--fastboot` to `flash.py`).
3. **Battery above 3.7 V** — `flash.py` refuses below that.
4. The phone is the supported hardware combination (ILI9881H C3I panel,
   KTD3137 backlight), see [01-hardware.md](01-hardware.md). Other units boot
   to the desktop but without touch and brightness control.
5. The two images in `dist/`: a `redmi8-ubuntu-<date>-userdata.img` (with its
   `.sha256`) and `lk2nd-olive-20260920.img`. They are not in the git
   repository; build them as described in [02-building.md](02-building.md).

## Flashing

Power the phone off, then hold **Volume-Down + Power** until the FASTBOOT
screen shows. That is the stock bootloader's fastboot; it is in `aboot`, so no
broken kernel or image can take it away.

```bash
python scripts/flash/flash.py                  # checks only, writes nothing
python scripts/flash/flash.py --flash --reboot
```

It checks the image checksum and sparse structure, that the device is an
unlocked `olive` in stock fastboot (`kernel=lk`), the battery, and that both
images fit. Then:

| Partition | Image | Size |
|---|---|---|
| `userdata` | `dist/redmi8-ubuntu-<date>-userdata.img` | ~2.7 GB sparse, 4.4 GiB expanded |
| `boot` | `dist/lk2nd-olive-20260920.img` | 320 KiB |

Nothing else on the phone is written. If a write fails the script stops with
the phone still in fastboot; run it again.

## First boot

* lk2nd shows its menu for 2 s, then starts `olive-main`.
* The initramfs grows the root partition and filesystem to the whole
  `userdata` partition (~50 GB); this first boot takes about a minute.
* GNOME logs `user` in automatically. Password `1234`, root locked.
* Over USB the phone is `172.16.43.1` and gives the PC an address by DHCP
  (`172.16.43.1xx`, no gateway, so the PC's internet is not affected).

Then, from the PC:

```bash
pip install paramiko
python scripts/install/personalize.py --password NEW --wifi MYSSID --root-key KEY.pub
```

* `--password` replaces `1234` (do it; SSH accepts passwords).
* `--wifi` writes a NetworkManager profile; the passphrase is prompted for, or
  read from `WIFI_PSK`, and never appears on a command line.
* `--root-key` lets root log in with that public key.

Wi-Fi can equally be joined from the GNOME menu.

## Everyday use

* **Power key:** logind ignores a short press (so the phone does not suspend,
  which it cannot resume from); a long press powers off. Shut down from the
  GNOME menu.
* **Updates:** `sudo apt update && sudo apt upgrade` works. The kernel is not
  an Ubuntu package and is never replaced by apt. Mesa is Ubuntu's; its
  freedreno driver is what renders the desktop.
* **Wi-Fi is 2.4 GHz only** and runs on legacy rates (see known issues).

## If it does not come up

| What you see | What it means | What to do |
|---|---|---|
| Xiaomi logo, then back to fastboot / lk2nd | `boot` or `userdata` wrong | flash again |
| Boot text, then black, USB network up | kernel is fine, userspace hung | `telnet 169.254.66.1` (rescue shell in the initramfs; Windows needs a few minutes for its own 169.254.x address there, the DHCP server only runs in Ubuntu), or wait: after 3 unconfirmed boots the initramfs stops before userspace and keeps the rescue shell |
| Desktop but no touch/brightness | other panel/backlight variant | see [01-hardware.md](01-hardware.md) |
| Nothing at all | — | hold Power ~15 s (hard reset), then Volume-Down + Power |

**Rescue entry:** the lk2nd menu (Volume keys during the 2 s timeout) offers
`olive-r6-safe`: the previous kernel in text mode without display drivers,
with USB network and SSH. `olive.test=r7` on a test entry's command line makes
the initramfs switch the default to that entry *before* anything risky runs,
so any reset afterwards comes back safe.

**Rescue shell:** in the initramfs, `touch /tmp/go` continues a stopped boot;
`echo 0 > /sysroot/var/lib/olive/bootcount` resets the counter.

## Back to Android

Flash the stock `boot` image of your MIUI release (from the fastboot ROM, or
from the backup you took before installing) and clear `userdata`:

```bash
fastboot flash boot boot.img
fastboot erase userdata      # MIUI needs an empty data partition to start
fastboot reboot
```
