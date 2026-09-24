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
hardware? The answer turned out to be yes, with honest limits. The desktop
is rendered on the phone's own GPU, the touchscreen takes ten fingers, the
battery and the charger show up in the system, Wi-Fi works, and the phone
boots to the desktop in about seventeen seconds.

And that second life can be useful. Many people rent a VPS to run a
self-hosted AI agent, a bot, a home automation hub or a small web service.
An old phone like this can be that machine instead: an eight-core ARM64
computer with 4 GB of RAM, Wi-Fi and a 5000 mAh battery that bridges power
cuts, sitting on your desk, costing nothing per month, drawing a few watts,
with your data staying at home. You reach it over SSH like any server, and
it still has a touchscreen and a desktop when you want to look at it. This
repository shows, step by step, how to get there, and the same way of
working carries over to other old phones.

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

You build the system yourself, from this repository and public sources
only: the kernel, the lk2nd bootloader, the initramfs and a clean, ordinary
Ubuntu. It is the same base system as the two sister projects for the
Galaxy S9+ and the Mi 9T, plus only the few pieces this phone's hardware
needs. Nothing of ours is preinstalled; the GNOME tweaks for the notch screen
and the debugging tools are kept separate as extras you can add. The image
has no default password: you choose one when you build it, root is locked,
and every phone creates its own SSH keys on its first boot.

It is fair to say what does not work yet. There is no sound, no camera, no
mobile network (no calls, no SMS, no mobile data), no GPS and no fingerprint
reader. The phone cannot sleep and wake up again, so it stays on. Wi-Fi is
2.4 GHz only and slower than it could be. And Xiaomi built the Redmi 8 with
several different display and backlight suppliers: this port supports one
combination. On another unit the desktop still appears, but touch and
brightness control will not work.

Installing this erases the phone's user data. The Android system partitions
themselves stay untouched, so the way back to Android is always open, but
you should only try this on a phone you are prepared to experiment with,
with an unlocked bootloader and a backup of everything you care about.
Questions, fixes and reports from other units are very welcome.

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
  ->  initramfs (Ubuntu initramfs-tools + this port's hooks: USB rescue, boot counter)
  ->  switch_root into Ubuntu on userdata p2
```

Stock fastboot (Volume-Down + Power) lives in `aboot` and is never
overwritten, so the phone can always be reflashed.

### What works

| Subsystem | State | How |
|---|---|---|
| Boot | stock lk → lk2nd → extlinux, **16.9 s** to GNOME on the reference phone | lk2nd, initramfs with rescue hooks |
| Display | 720x1520 via the bootloader's framebuffer (`simpledrm`) | the msm DSI path does not bring the panel up yet |
| GPU | GNOME renders on the Adreno 505; 19 MHz idle, 450 MHz under load | msm GPU-only (`separate_gpu_kms=1`) + Mesa `kmsro`, zap shader, 3 kernel fixes |
| Backlight | brightness slider | own driver `ktd3137-backlight` |
| Touch | 10 fingers | own driver `ili9881h-tddi-fb` (RAM firmware at probe) |
| Battery / USB | UPower: percentage, charging/full, charger online | own read-only driver `olive-power` (PMI632) |
| Wi-Fi | NetworkManager, GNOME menu, 0 % loss, 1–2 ms | wcn36xx, **legacy rates only** (`olive-wifi-noht`) |
| USB | NCM network, phone at `172.16.43.1`, DHCP for the PC (no gateway) | configfs gadget from the initramfs |
| Rescue | USB telnet in the initramfs; 3 unconfirmed boots stop before userspace | `device/base/etc/initramfs-tools/`, `olive-autoconfirm.timer` |
| Memory | 1.8 GB zram swap (zstd) | `systemd-zram-generator` |
| Desktop | GNOME 46 with the on-screen keyboard; notch-aware top bar as an extra | extra `phone-ui` |
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
| Every boot took 27 s | a 10 s diagnostic gate in the first initramfs | no gate: 16.9 s |
| A bad kernel could leave the phone unreachable | no rescue path before userspace | USB telnet before root discovery, boot counter, automatic rollback entry |

### Build your own system

Everything is built from this repository and public sources; no image is
downloaded from us. You need the phone with an unlocked bootloader (Xiaomi
Mi Unlock), a Linux build host (Ubuntu 24.04, a VM or WSL2 works),
`fastboot` and Python 3.

```bash
# 1. kernel, modules and the three own drivers (clang)
scripts/build/build-kernel.sh

# 2. Ubuntu, initramfs, boot partition and lk2nd: asks for your password
sudo image/build-image.sh

# 3. phone in stock fastboot (power off, Volume-Down + Power): checks first
python scripts/flash/flash.py
python scripts/flash/flash.py --flash --reboot
```

What the image contains: the common base system of all three phone projects
([`image/common/README.md`](image/common/README.md): Ubuntu 24.04, GNOME,
Firefox, SSH, no default password, root locked, SSH keys made on the phone),
plus this phone's hardware layer in [`device/`](device/): the kernel modules,
the GPU and touch firmware, msm-firmware-loader for the phone's own Wi-Fi
calibration, the GPU start-up, the Wi-Fi fix, the USB network and the
initramfs rescue hooks. Over USB the phone is `172.16.43.1` and hands the PC
an address. Details: [docs/02-building.md](docs/02-building.md),
[docs/03-installing.md](docs/03-installing.md).

### Extras (optional, never installed by the image build)

```bash
sudo extras/install.sh                    # list them
sudo extras/install.sh phone-ui           # install one; --remove takes it out again
```

| Extra | What it does |
|---|---|
| [phone-ui](extras/phone-ui/) | top bar clear of the notch and the rounded corners, windows open maximized, dark theme, dock favourites |
| [debug-tools](extras/debug-tools/) | `olive-report` (one-shot hardware report) and a persistent journal |

### Repository layout

```
kernel/
  config-7.1.3-msm89x7-olive-r7   the kernel's .config
  patches/                        ordered patch steps + apply-all.sh
  modules/                        the three out-of-tree drivers (+ Kbuild)
  devicetree/                     kernel-built DTB, the three edits, final DTB
  downstream-reference/           Xiaomi 4.9 sources and stock DT, for reference
image/                            build the whole system image and lk2nd
                                  (common/ is shared by all three phones)
device/                           the hardware layer of the image, incl. the initramfs hooks
extras/                           optional features, installed on request
firmware/                         zap shader, touch firmware + converter
scripts/
  build/                          build the kernel and the out-of-tree drivers
  flash/                          flash.py
docs/                             everything in detail
```

### Documentation

| | |
|---|---|
| [01-hardware.md](docs/01-hardware.md) | the board: buses, addresses, the boot chain, what differs between Redmi 8 units |
| [02-building.md](docs/02-building.md) | kernel, modules, DTB, initramfs and the flashable image |
| [03-installing.md](docs/03-installing.md) | flashing, first boot, rescue, back to Android |
| [04-drivers.md](docs/04-drivers.md) | every driver and kernel fix, and why it exists |
| [05-performance.md](docs/05-performance.md) | the numbers and how they were measured |
| [06-known-issues.md](docs/06-known-issues.md) | what does not work and what was tried |

### Acknowledgements

This port builds on the [msm89x7-mainline](https://github.com/msm89x7-mainline/linux)
kernel, [lk2nd](https://github.com/msm8916-mainline/lk2nd) and postmarketOS'
msm-firmware-loader and device work for the MSM8937 family.

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
