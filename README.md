# Ubuntu on the Xiaomi Redmi 8

This is a Xiaomi Redmi 8 that no longer runs Android. It boots a current
mainline Linux kernel and a completely ordinary Ubuntu 24.04 with the GNOME
desktop, the same system you would install on a laptop. Firefox comes from
Mozilla's own repository, updates come from Ubuntu with `apt`, and the phone
behaves like a small Linux computer with a touchscreen.

The Redmi 8 is a cheap phone from 2019, and there are millions of them in
drawers. Android support for it ended long ago. This project started with a
simple question: can such a phone be given a second life as a real Linux
machine, not as a container inside Android, but with Linux in charge of the
hardware? The answer turned out to be yes, with honest limits. The desktop is
rendered on the phone's own GPU, the touchscreen takes ten fingers, the
battery and the charger show up in the system, Wi-Fi works, and the phone
boots to the desktop in about seventeen seconds.

Getting there was not a straight road. The display chip, the touch
controller and the backlight driver on this particular board were not
supported by mainline Linux at all, so they got their own small drivers. The
graphics chip first rendered everything as zeros, then reset the whole phone
whenever it woke up, then ran at the wrong clock speed; each of those was a
separate fault that hid the next. Wi-Fi connected fine and then quietly lost
most of what the phone sent, which turned out to be a driver problem with
one specific 802.11n feature. None of this is visible any more when you use
the phone, and all of it is written down here, so the next person does not
have to find it again.

It is fair to say what does not work yet. There is no sound, no camera, no
mobile network (no calls, no SMS, no mobile data), no GPS and no fingerprint
reader. The phone cannot sleep and wake up again, so it stays on. Wi-Fi is
2.4 GHz only and slower than it could be. And Xiaomi built the Redmi 8 with
several different display and backlight suppliers: this port supports one
combination. On another unit the desktop still appears, but touch and
brightness control will not work.

Installing this erases the phone's user data. The Android system partitions
themselves stay untouched, so the way back to Android is always open, but
you should only try this on a phone you are prepared to experiment with, with
an unlocked bootloader and a backup of everything you care about.

If you own a Redmi 8 and want to try it, study how it works, or port the
same ideas to a related phone, everything needed is in this repository: the
kernel changes, the drivers, the device tree, the parts of Ubuntu that are
specific to this phone, the build and flash tools, and a detailed record of
every problem and how it was solved. Questions, fixes and reports from other
units are very welcome.

---

## Technical overview

```
SoC        Qualcomm SDM439 (8x Cortex-A53: 4 @ 1.96 GHz + 4 @ 1.46 GHz)
GPU        Adreno 505, freedreno (Mesa 25.2), up to 450 MHz
Display    720x1520 IPS, ILITEK ILI9881H (C3I/Tianma), MIPI DSI 12 nm PHY
Touch      ILITEK TDDI in the panel IC, SPI
Memory     4 GB (3.6 GB usable), 64 GB eMMC
PMIC       PM8953 + PMI632 (SMB5 charger, QG fuel gauge), 5000 mAh
Wi-Fi/BT   WCN3620-class pronto (wcn36xx), 2.4 GHz only
Kernel     7.1.3-msm89x7-olive-r7 (msm89x7-mainline v7.1.3-r1 + this port)
Userland   Ubuntu 24.04 LTS arm64, GNOME 46 on Wayland
```

### Boot chain

```
stock Xiaomi lk (aboot, unlocked)  ->  lk2nd on the boot partition
  ->  extlinux.conf on userdata p1  ->  vmlinuz + initramfs + DTB
  ->  postmarketOS initramfs (USB rescue, boot counter)
  ->  switch_root into Ubuntu on userdata p2
```

Stock fastboot (Volume-Down + Power) lives in `aboot` and is never
overwritten, so the phone can always be reflashed.

### What works

| Subsystem | State | How |
|---|---|---|
| Boot | stock lk → lk2nd → extlinux, **16.9 s** to GNOME | lk2nd, pmOS initramfs (modified) |
| Display | 720x1520 via the bootloader's framebuffer (`simpledrm`) | the msm DSI path does not bring the panel up yet |
| GPU | GNOME renders on the Adreno 505; 19 MHz idle, 450 MHz under load | msm GPU-only (`separate_gpu_kms=1`) + Mesa `kmsro`, zap shader, 3 kernel fixes |
| Backlight | brightness slider | own driver `ktd3137-backlight` |
| Touch | 10 fingers | own driver `ili9881h-tddi-fb` (RAM firmware at probe) |
| Battery / USB | UPower: percentage, charging/full, charger online | own read-only driver `olive-power` (PMI632) |
| Wi-Fi | NetworkManager, GNOME menu, 0 % loss, 1–2 ms | wcn36xx, **legacy rates only** (`olive-wifi-noht`) |
| USB | NCM network, phone at `172.16.43.1`, DHCP for the PC (no gateway) | configfs gadget from the initramfs |
| Rescue | USB telnet in the initramfs; 3 unconfirmed boots stop before userspace | `initramfs/init_2nd.sh`, `olive-autoconfirm.timer` |
| Memory | 1.8 GB zram swap (zstd) | `systemd-zram-generator` |
| Desktop | GNOME 46, Yaru dark, on-screen keyboard, notch-aware top bar | extension `olive-display@redmi8` |
| Stability | watchdog 20 s / 30 s, panic on hung task, reboot after 10 s | systemd + sysctl |
| Not working | audio, camera, modem, sensors, GPS, fingerprint, CPU idle, suspend | [docs/06-known-issues.md](docs/06-known-issues.md) |

### Hurdles that were overcome

Each of these cost at least one failed boot or a lot of measuring. The order is
the order they were found; each one hid the next.

| Symptom | Cause | Fix |
|---|---|---|
| Screen goes dark as soon as the kernel loads its backlight driver | the device tree says LM3697, this unit has a Kinetic KTD3137 at the same I²C address; the LM3697 reset sequence switched it off | own `ktd3137-backlight` driver + DT edit (`1-dtb-ktd3137.py`) |
| Touch never reports anything | the touch controller sits inside the display IC, loses its firmware on every reset, and only scans while the panel is fed video | own driver loads the RAM firmware at probe; relies on the bootloader keeping the panel running |
| The GPU renders only zeros, without any error | mainline never loaded the Adreno zap shader through TrustZone for this board | DT `zap-shader` node + `a506_zap` firmware from the stock `vendor` partition |
| Hard SoC reset whenever the GPU wakes up | the A505 has CPZ retention like the A506; the zap *resume* SCM call resets the SoC | skip zap resume for A505 (`10-gpu-zap-a505.py`) |
| GPU at 700 MHz instead of 450 MHz | GPLL3's post-divider was declared with width 0, so it was ignored | width 4 (`09-fix-gpll3-width.py`) |
| Wi-Fi connects, then 50–80 % of what the phone sends is lost | wcn36xx sets up an 802.11n TX Block-Ack session that breaks transmit | associate without HT (`olive-wifi-noht`): 0 % loss, 1–2 ms |
| No battery at all in the system | mainline has no PMI632 charger or gauge driver | own read-only `olive-power`: coulomb counting seeded from the open-circuit voltage |
| Every boot took 27 s | a 10 s diagnostic gate in the initramfs | gate only with `olive.gate` on the command line: 16.9 s |
| A bad kernel could leave the phone unreachable | no rescue path before userspace | USB telnet before root discovery, boot counter, automatic rollback entry |

### Repository layout

```
kernel/
  config-7.1.3-msm89x7-olive-r7   the running kernel's .config
  patches/                        ordered patch steps + apply-all.sh
  modules/                        the three out-of-tree drivers (+ Kbuild)
  devicetree/                     kernel-built DTB, the three edits, final DTB
  downstream-reference/           Xiaomi 4.9 sources and stock DT, for reference
initramfs/                        the modified init_2nd.sh
device/
  rootfs/                         every file the port adds to Ubuntu
  gnome-user-settings.ini         the GNOME settings of the image
firmware/                         zap shader, touch firmware + converter
scripts/
  build/                          build the modules, edit the initramfs
  image/                          make-image.sh / verify-image.sh (run on a phone)
  flash/                          flash.py
  install/                        personalize.py
docs/                             everything in detail
```

### Installing

You need an unlocked bootloader (Xiaomi Mi Unlock), a USB cable, Android
platform-tools (`fastboot`) and Python 3 on the PC, and the two images in
`dist/`: `redmi8-ubuntu-<date>-userdata.img` and `lk2nd-olive-20260920.img`.
The images are several gigabytes and are **not stored in git**; they are made
from a running system, see [docs/02-building.md](docs/02-building.md).

```bash
# phone: power off, then hold Volume-Down + Power -> FASTBOOT
python scripts/flash/flash.py                  # checks only
python scripts/flash/flash.py --flash --reboot

# after GNOME is up (first boot ~1 min): password, Wi-Fi, root key
python scripts/install/personalize.py --password NEW --wifi MYSSID --root-key KEY.pub
```

Default login `user` / `1234`, root locked. **Change the password** —
`personalize.py --password` does it. Rescue and the way back to Android:
[docs/03-installing.md](docs/03-installing.md).

### Building

```bash
kernel/patches/apply-all.sh <msm89x7-v7.1.3-r1-tree> <pmaports-0001-0003-dir>
make -C <tree> ARCH=arm64 LLVM=1 olddefconfig
make -C <tree> ARCH=arm64 LLVM=1 -j$(nproc) Image.gz modules qcom/sdm439-xiaomi-olive.dtb
scripts/build/build-modules.sh <tree>
```

Details, the device-tree edits and the image build:
[docs/02-building.md](docs/02-building.md).

### Documentation

| | |
|---|---|
| [01-hardware.md](docs/01-hardware.md) | the board: buses, addresses, the boot chain, what differs between Redmi 8 units |
| [02-building.md](docs/02-building.md) | kernel, modules, DTB, initramfs and the flashable image |
| [03-installing.md](docs/03-installing.md) | flashing, first boot, rescue, back to Android |
| [04-drivers.md](docs/04-drivers.md) | every driver and kernel fix, and why it exists |
| [05-performance.md](docs/05-performance.md) | the numbers and how they were measured |
| [06-known-issues.md](docs/06-known-issues.md) | what does not work and what was tried |

### Related projects

The same idea, Ubuntu on mainline Linux, on two other phones:

* [Samsung Galaxy S9+ (Exynos 9810)](https://github.com/SheroAbi/galaxy-s9plus-mainline-linux)
* [Xiaomi Mi 9T (Snapdragon 730)](https://github.com/SheroAbi/mi9t-mainline-linux)

### Licence

GPL-2.0-only for drivers, patches and device trees, see [LICENSE](LICENSE).
Firmware and reference files keep their own terms, listed in
[THIRD-PARTY.md](THIRD-PARTY.md).

This is a hobby project and comes without any warranty. Flashing a phone can
go wrong; you do it at your own risk.
