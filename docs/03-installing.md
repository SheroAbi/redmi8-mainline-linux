# Installing

## What has to be true first

1. **Bootloader unlocked** (Xiaomi Mi Unlock; `fastboot getvar unlocked` → `yes`).
2. **Android platform-tools** on the PC (`fastboot` on the `PATH`, or pass
   `--fastboot` to `flash.py`).
3. **Battery above 3.7 V** — `flash.py` refuses below that.
4. The phone is the supported hardware combination (ILI9881H C3I panel,
   KTD3137 backlight), see [01-hardware.md](01-hardware.md). Other units boot
   to the desktop but without touch and brightness control.
5. The images from [02-building.md](02-building.md) in `dist/image/`:
   `userdata.img`, `lk2nd.img`, `SHA256SUMS`.

## Flashing

Power the phone off, then hold **Volume-Down + Power** until the FASTBOOT
screen shows. That is the stock bootloader's fastboot; it is in `aboot`, so no
broken kernel or image can take it away.

```bash
python scripts/flash/flash.py                  # checks only, writes nothing
python scripts/flash/flash.py --flash --reboot
```

It checks the images against `SHA256SUMS` and the sparse structure, that the
device is an unlocked `olive` in stock fastboot (`kernel=lk`), the battery,
and that both images fit. Then:

| Partition | Image | What it is |
|---|---|---|
| `userdata` | `dist/image/userdata.img` | the whole Ubuntu system: a disk image with `/boot` and `/` |
| `boot` | `dist/image/lk2nd.img` | lk2nd, which boots `extlinux.conf` from that disk image |

**Flashing userdata replaces all Android user data.**

Nothing else on the phone is written. If a write fails the script stops with
the phone still in fastboot; run it again.

## First boot

* lk2nd shows its menu for 2 s, then starts `ubuntu`.
* The root partition and filesystem grow to the whole `userdata` partition
  (~50 GB) and the phone creates its own SSH host keys.
* GDM logs your user in, GNOME on Wayland. The user and password are the ones
  you gave the image build; root is locked (use `sudo`), and root can never
  log in over SSH.
* Over USB the phone is `172.16.43.1` and gives the PC an address by DHCP
  (`172.16.43.1xx`, no gateway, so the PC's internet is not affected):
  `ssh <user>@172.16.43.1`.
* Wi-Fi: from the GNOME menu.

## What the image adds for this phone

On top of the common base system ([`image/common/README.md`](../image/common/README.md)),
only what the hardware needs (`device/base/`, enabled by `device/configure.sh`):

| | |
|---|---|
| the kernel modules and the three own drivers | touch, backlight, battery/charger |
| `firmware/`, `linux-firmware`, `msm-firmware-loader` | GPU zap shader, touch firmware, GPU microcode; Wi-Fi/ADSP/video firmware linked from the phone's own partitions |
| `olive-gpu` + service | loads msm GPU-only, then enables Mesa `kmsro` for the session |
| `olive-wifi-noht` + service | Wi-Fi without 802.11n TX aggregation (see [04-drivers.md](04-drivers.md)) |
| `olive-net`, `olive-watch`, `20-usb.network` | the USB network (systemd-networkd serves DHCP on `usb0`) |
| `olive-confirm-boot`, `olive-autoconfirm.timer` | resets the initramfs boot counter 90 s into a healthy boot |
| `initramfs-tools/` hooks | USB rescue shell, the userdata disk image, the boot counter |
| `modprobe.d/olive-staged.conf`, `modules-load.d/olive.conf` | modules that must not / must load |
| `logind.conf.d`, masked sleep targets | no suspend (it does not resume) |
| `90-olive-watchdog.conf`, `90-olive-debug.conf` | watchdog, and panic + reboot on a hung task |
| `90-olive-hide-android.rules` | hides the ~60 Android partitions from Files |
| `dconf/db/local.d/50-olive` | GNOME: power button does nothing, no automatic sleep |

The notch-aware top bar and the phone look of GNOME are optional:
[`extras/phone-ui`](../extras/phone-ui/).

## Everyday use

* **Power key:** logind ignores a short press (so the phone does not suspend,
  which it cannot resume from); a long press powers off. Shut down from the
  GNOME menu. The screen blanks after GNOME's idle time.
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

**Rescue shell:** `telnet 169.254.66.1` over the USB cable, as long as the
initramfs runs. `touch /tmp/go` continues a boot the counter stopped;
`echo 0 > /root/var/lib/olive/bootcount` resets the counter (the root
filesystem is mounted at `/root` there).

**Testing a kernel:** add a second `label` to `/boot/extlinux/extlinux.conf`
with the new kernel and keep the working one as `default`; the lk2nd menu
(Volume keys during the 2 s timeout) picks the test entry, and a plain reset
comes back to the working one.

## Back to Android

Flash the stock `boot` image of your MIUI release (from the fastboot ROM, or
from the backup you took before installing) and clear `userdata`:

```bash
fastboot flash boot boot.img
fastboot erase userdata      # MIUI needs an empty data partition to start
fastboot reboot
```
