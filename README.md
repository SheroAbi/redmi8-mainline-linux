# 📱 Ubuntu on the Xiaomi Redmi 8

[![build](https://github.com/SheroAbi/redmi8-mainline-linux/actions/workflows/build.yml/badge.svg)](https://github.com/SheroAbi/redmi8-mainline-linux/actions/workflows/build.yml)

**A completely ordinary Ubuntu 24.04 with GNOME on the Redmi 8, on mainline Linux 7.1.3.**
No Android underneath: Linux is in charge of the hardware, Firefox comes from
Mozilla, updates come from Ubuntu with `apt`. Your old phone becomes a small
Linux computer with a touchscreen.

- ♻️ **A second life:** a cheap 2019 phone that Android dropped long ago, of which millions sit in drawers.
- ⚡ **Fast boot:** to the GNOME desktop in about 17 seconds.
- 🖥️ **Real GPU desktop:** GNOME on Wayland rendered by the Adreno 505, with the on-screen keyboard.
- 👆 **Touch, brightness, battery:** 10-finger touch, brightness slider, battery and charger in the system, each with its own small driver.
- 📶 **Stable Wi-Fi:** 0 % packet loss and 1–2 ms latency, and a USB network to the PC on the same cable.
- 🛟 **Hard to brick:** stock fastboot is never overwritten, and a USB rescue shell plus a boot counter catch a bad kernel.
- 🔒 **Yours:** you build it yourself from public sources. No default password, root locked, SSH keys made on the phone.
- 💸 **A free home server:** 8 cores, 4 GB RAM, a 5000 mAh battery as a built-in UPS, a few watts. Run your bot, AI agent or home automation on it instead of renting a VPS.

> ⚠️ Xiaomi built the Redmi 8 with several display and backlight suppliers.
> This port supports **one combination** (ILI9881H C3I panel + KTD3137
> backlight). On other units the desktop still appears, but touch and
> brightness control will not work. *(Hobby project, not affiliated with Xiaomi.)*

---

## ✨ What works

| Subsystem | State | How |
|---|---|---|
| Boot | stock lk → lk2nd → extlinux, **16.9 s** to GNOME | lk2nd, initramfs with rescue hooks |
| Display | 720x1520 via the bootloader's framebuffer (`simpledrm`) | the msm DSI path does not bring the panel up yet |
| GPU | GNOME renders on the Adreno 505; 19 MHz idle, 450 MHz under load | msm GPU-only + Mesa `kmsro`, zap shader, 3 kernel fixes |
| Backlight | brightness slider | own driver `ktd3137-backlight` |
| Touch | 10 fingers | own driver `ili9881h-tddi-fb` |
| Battery / USB | percentage, charging/full, charger online | own read-only driver `olive-power` (PMI632) |
| Wi-Fi | GNOME menu, 0 % loss, 1–2 ms | wcn36xx, legacy rates (`olive-wifi-noht`) |
| USB | network to the PC: phone at `172.16.43.1`, DHCP for the PC (no gateway) | configfs gadget from the initramfs |
| Rescue | USB telnet in the initramfs; 3 unconfirmed boots stop before userspace | initramfs hooks + `olive-autoconfirm.timer` |
| Memory | 1.8 GB zram swap (zstd) | `systemd-zram-generator` |
| Stability | watchdog, panic on a hung task, reboot after 10 s | systemd + sysctl |

**Not working (yet):** sound, camera, mobile network (calls, SMS, data), GPS,
fingerprint reader, sensors, suspend (the phone stays on). Wi-Fi is 2.4 GHz
only and slower than it could be. Details: [docs/06-known-issues.md](docs/06-known-issues.md).

---

## 🛠️ Build it yourself

Everything is built from this repository and public sources: kernel, lk2nd,
initramfs and a clean Ubuntu. No image is downloaded from us.
These exact steps run on every change on a fresh Ubuntu 24.04 machine
([build](https://github.com/SheroAbi/redmi8-mainline-linux/actions/workflows/build.yml)).

**You need:** a Redmi 8 (olive) with an **unlocked bootloader** (Xiaomi Mi
Unlock), a **Linux** build host (Ubuntu 24.04 on a PC or in a VM; WSL2 works
too), `fastboot` and Python 3.

```bash
git clone https://github.com/SheroAbi/redmi8-mainline-linux.git
cd redmi8-mainline-linux

# 0. host packages (once)
sudo apt install git make clang lld llvm bc bison flex libssl-dev libelf-dev \
    python3 zstd debootstrap qemu-user-static binfmt-support e2fsprogs \
    openssl curl fdisk gcc-arm-none-eabi device-tree-compiler python3-libfdt

# 1. kernel, modules and the three own drivers (as your normal user)
scripts/build/build-kernel.sh

# 2. Ubuntu, initramfs, boot partition and lk2nd (asks for your password)
sudo image/build-image.sh
```

Good to know:
- 📁 The kernel builds in `~/redmi8-build` (`WORK=` to move it); the image work directory is `/var/tmp/redmi8-image`.
- 📌 The kernel is pinned to `msm89x7-mainline/linux` tag `v7.1.3-r1`; the patches in `kernel/patches/` are replayed on it in order.
- 🧩 The output lands in `dist/image/`: `userdata.img`, `lk2nd.img` and `SHA256SUMS`.

---

## 📲 Install

Power the phone off, then hold **Volume-Down + Power** until the FASTBOOT screen shows:

```bash
python3 scripts/flash/flash.py                   # checks only, writes nothing
python3 scripts/flash/flash.py --flash --reboot  # write and start
```

It checks the images, that the phone is an unlocked `olive` in stock
fastboot, that the battery is above 3.7 V and that both images fit.

> ⚠️ **This erases all Android user data** (`userdata`). The Android system
> partitions stay untouched, so the way back to Android is always open:
> flash your stock `boot` image and erase `userdata`.

**First boot:** lk2nd shows its menu for 2 s, the root filesystem grows to
the whole partition (~50 GB), the phone makes its own SSH keys, and GNOME
logs your user in. Over USB: `ssh <user>@172.16.43.1`. Wi-Fi is set up from
the GNOME menu. Details: [docs/03-installing.md](docs/03-installing.md).

---

## 🧩 Extras (optional)

Nothing of ours is preinstalled. Add these on the phone if you want them:

```bash
sudo extras/install.sh                    # list them
sudo extras/install.sh phone-ui           # install one; --remove takes it out again
```

| Extra | What it does |
|---|---|
| [phone-ui](extras/phone-ui/) | top bar clear of the notch and the rounded corners, windows open maximized, dark theme, dock favourites |
| [debug-tools](extras/debug-tools/) | `olive-report` (one-shot hardware report) and a persistent journal |

---

## 🛟 Troubleshooting

| Problem | Fix |
|---|---|
| Xiaomi logo, then back to fastboot / lk2nd | `boot` or `userdata` is wrong: flash again. |
| Boot text, then black, USB network up | Userspace hung. `telnet 169.254.66.1` over the cable for the rescue shell; after 3 unconfirmed boots the initramfs stops there on its own. |
| Desktop, but no touch or brightness | Another panel/backlight variant ([docs/01-hardware.md](docs/01-hardware.md)). Reports from other units are very welcome. |
| Nothing at all | Hold Power ~15 s (hard reset), then Volume-Down + Power for fastboot. |
| `flash.py` refuses: battery | Charge above 3.7 V first. |
| Short press on the power key does nothing | On purpose: the phone cannot resume from suspend. Long press powers off. |

---

## 🔬 Under the hood

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

**Boot chain:** stock Xiaomi lk (aboot, unlocked) → lk2nd on `boot` →
`extlinux.conf` on userdata p1 → kernel + initramfs + DTB → initramfs
(USB rescue, boot counter) → `switch_root` into Ubuntu on userdata p2.
Stock fastboot lives in `aboot` and is never overwritten.

### 🧗 Hurdles that were overcome

<details>
<summary>Each of these cost at least one failed boot, and each hid the next (click to open)</summary>

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

</details>

### 🗂️ Repository layout

```text
kernel/
  config-7.1.3-msm89x7-olive-r7   the kernel's .config
  patches/                        ordered patch steps + apply-all.sh
  modules/                        the three out-of-tree drivers (+ Kbuild)
  devicetree/                     kernel-built DTB, the three edits, final DTB
  downstream-reference/           Xiaomi 4.9 sources and stock DT, for reference
image/                            build the whole system image and lk2nd (common/ is shared by all three phones)
device/                           the hardware layer of the image, incl. the initramfs hooks
extras/                           optional features, installed on request
firmware/                         zap shader, touch firmware + converter
scripts/build/                    build the kernel and the out-of-tree drivers
scripts/flash/                    flash.py
docs/                             everything in detail
```

### 📚 Documentation

| | |
|---|---|
| [01-hardware.md](docs/01-hardware.md) | the board: buses, addresses, the boot chain, what differs between Redmi 8 units |
| [02-building.md](docs/02-building.md) | kernel, modules, DTB, initramfs and the flashable image |
| [03-installing.md](docs/03-installing.md) | flashing, first boot, rescue, back to Android |
| [04-drivers.md](docs/04-drivers.md) | every driver and kernel fix, and why it exists |
| [05-performance.md](docs/05-performance.md) | the numbers and how they were measured |
| [06-known-issues.md](docs/06-known-issues.md) | what does not work and what was tried |

---

## 🙏 Acknowledgements

This port builds on the [msm89x7-mainline](https://github.com/msm89x7-mainline/linux)
kernel, [lk2nd](https://github.com/msm8916-mainline/lk2nd) and postmarketOS'
msm-firmware-loader and device work for the MSM8937 family.

**Same idea, other phones:**
[Samsung Galaxy S9+ (Exynos 9810)](https://github.com/SheroAbi/galaxy-s9plus-mainline-linux) ·
[Xiaomi Mi 9T (Snapdragon 730)](https://github.com/SheroAbi/mi9t-mainline-linux)

---

## 🇩🇪 Kurz auf Deutsch

Dieses Projekt gibt dem Xiaomi Redmi 8 ein zweites Leben: ein **ganz normales
Ubuntu 24.04 mit GNOME** auf aktuellem Mainline-Kernel 7.1.3, ohne Android
darunter. GPU, Touch, Helligkeit, Akku, WLAN und ein USB-Netz zum PC laufen,
Start in rund 17 Sekunden. Ideal als stromsparender Heimserver statt VPS.
Gebaut wird alles selbst auf einem Linux-Rechner:
`scripts/build/build-kernel.sh` → `sudo image/build-image.sh` →
`python3 scripts/flash/flash.py --flash --reboot` im Fastboot-Modus.
**Achtung:** Die Android-Nutzerdaten werden gelöscht; der Weg zurück zu
Android bleibt offen. Unterstützt ist eine Display-/Backlight-Kombination.

---

## 📄 License

GPL-2.0-only for drivers, patches and device trees, see [LICENSE](LICENSE).
Firmware and reference files keep their own terms, listed in
[THIRD-PARTY.md](THIRD-PARTY.md).

This is a hobby project and comes without any warranty. Flashing a phone can
go wrong; you do it at your own risk. Questions, fixes and reports from other
units are very welcome.
