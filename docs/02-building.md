# Building

A complete, flashable system in two commands, from public sources only:

```bash
scripts/build/build-kernel.sh      # kernel, modules, the three own drivers (normal user)
sudo image/build-image.sh          # Ubuntu, initramfs, boot partition, lk2nd
```

| Piece | Built from | Lands in |
|---|---|---|
| Kernel `vmlinuz` + in-tree modules | msm89x7 `v7.1.3-r1` + `kernel/patches/` + `kernel/config-*` | boot partition `/ubuntu/vmlinuz`, `/usr/lib/modules/7.1.3-msm89x7-olive-r7/kernel` |
| Out-of-tree drivers | `kernel/modules/` | `/usr/lib/modules/…/extra/*.ko` |
| Device tree | `kernel/devicetree/sdm439-xiaomi-olive.dtb` (checked in, see below) | boot partition `/ubuntu/sdm439-xiaomi-olive.dtb` |
| Initramfs | Ubuntu's `initramfs-tools` + `device/base/etc/initramfs-tools/` | boot partition `/ubuntu/initramfs` |
| Root filesystem | debootstrap + [`image/common/`](../image/common/README.md) + `device/` | `userdata`, partition 2 of the disk image |
| lk2nd | upstream `msm8916-mainline/lk2nd` @ `8b46487c` (2026-09-20), target `lk2nd-msm8952` | `boot` |

Built artefacts land in `dist/` (kernel staging in `~/redmi8-build`), which git ignores.

## Build host

Ubuntu 24.04 (a VM or WSL2 works). The kernel is built with clang
(`make ARCH=arm64 LLVM=1`; the reference kernel used clang 18.1.3):

    sudo apt install git make clang lld llvm bc bison flex libssl-dev libelf-dev \
        python3 zstd debootstrap qemu-user-static binfmt-support e2fsprogs \
        fdisk openssl curl gcc-arm-none-eabi python3-libfdt device-tree-compiler

Keep the work directories on a Linux filesystem (not under `/mnt/c` in WSL).

## 1. Kernel

```bash
scripts/build/build-kernel.sh
```

Clones `msm89x7-mainline/linux` tag `v7.1.3-r1` into `~/redmi8-build/linux`
(`WORK=` to change it), applies the patch steps in order
(`kernel/patches/apply-all.sh`, details in its README), builds `Image.gz` and
the modules with the shipped config, builds the three out-of-tree drivers,
and stages everything in `~/redmi8-build/kernel/`.

| # | Step | Changes |
|---|---|---|
| 00 | `00-olive-display-touch-v2.patch` | panel node and supplies, generated ILI9881H+ panel driver |
| 0001 | `0001-soc-qcom-ubwc-add-sdm439.patch` | UBWC entry for the SDM439 (the GPU does not probe without it) |
| 01 | `01-dts-touch-backlight-gpu.py` | touch SPI node, backlight wiring, GPU node enabled |
| 02 | `02-add-touch-driver.py` | ILI9881H TDDI touch driver in-tree |
| 03 | `03-port-dsi-phy-12nm.py` | 12 nm DSI PHY driver ported (`dsi_phy_12nm.c`), PHY timings, `LOCALVERSION=-msm89x7-olive-r7` |
| 04 | `04-fix-dsi-pll-rate.py` | 12 nm PLL: SSC fractional `recalc_rate` |
| 05 | `05-touch-ram-firmware.py` | touch: RAM firmware load, coordinate clamp |
| 06 | `06-touch-panel-follower.py` | touch as DRM panel follower; a5xx TRAP_LOG fix |
| 07 | `07-touch-firmware-query.py` | touch firmware query before IRQ enable |
| 08 | `08-fix-dsi-phy-range.py` | 12 nm PHY: sync the PLL range |
| 09 | `09-fix-gpll3-width.py` | **GPLL3 post-divider width 0 → 4** (GPU 450 MHz, not 700) |
| 10 | `10-gpu-zap-a505.py` | **A505 skips zap resume**, DT: zap-shader, `gpu_zap_mem`, ramoops |

`CONFIG_MODULE_SIG` is on but not forced, so modules from another build of the
same version load (they taint the kernel).

> **Honest limit.** The tree that built the reference kernel no longer
> exists. The steps above were reconstructed from the scripts that built it;
> patch 0001 was recovered from the reference kernel's own `ubwc_config.ko`
> (it maps `qcom,sdm439` to `msm8937_data`). The reference build also carried
> two DSI-only device-tree patches from a local pmaports cache; the display
> path they touch is switched off in the device tree the phone boots, so they
> are not needed. A rebuild gives a functionally equal kernel, not a
> bit-identical one. Please open an issue if a step does not apply.

The out-of-tree drivers alone, against any configured 7.1.3 msm89x7 tree:

```bash
scripts/build/build-modules.sh <tree>
```

## 2. Device tree

The boot device tree is checked in: `kernel/devicetree/sdm439-xiaomi-olive.dtb`,
byte-identical to the one on the reference phone. It is the kernel-built tree
(`sdm439-xiaomi-olive.kernel-built.dtb`) plus three edits, applied in order
with Python `fdt`:

| Script | Does |
|---|---|
| `1-dtb-ktd3137.py` | replaces the LM3697 node by `kinetic,ktd3137` @0x36 |
| `2-dtb-fbmode.py` | disables the MDSS (so msm binds only the GPU) and removes the touch → panel link |
| `3-dtb-power.py` | adds `xiaomi,olive-power` (charger@1000 + gauge) and ADC channel 0x4a |

```bash
cd kernel/devicetree
python 1-dtb-ktd3137.py sdm439-xiaomi-olive.kernel-built.dtb /tmp/1.dtb
python 2-dtb-fbmode.py  /tmp/1.dtb /tmp/2.dtb
python 3-dtb-power.py   /tmp/2.dtb sdm439-xiaomi-olive.dtb
```

## 3. The images

```bash
sudo image/build-image.sh
```

1. **Root filesystem:** debootstrap Ubuntu 24.04 arm64, the common package set
   and settings of all three phone projects
   ([`image/common/README.md`](../image/common/README.md)), then this phone's
   layer: the kernel modules, `firmware/` (GPU zap shader, touch firmware),
   `linux-firmware`, **msm-firmware-loader 1.8.0** (postmarketOS, MIT;
   downloaded and SHA-256 checked; it links the Wi-Fi, ADSP and video
   firmware from the phone's own Android partitions at every boot), and
   `device/base/` + `device/configure.sh`.
2. **Initramfs:** Ubuntu's `initramfs-tools` with this port's hooks
   (`device/base/etc/initramfs-tools/`):
   * a USB network and a telnet rescue shell on `169.254.66.1:23` before the
     root filesystem is looked for (USB only, never Wi-Fi),
   * the disk image on `userdata` attached as a loop device with partitions,
   * a boot counter: three boots that never reached `olive-autoconfirm.timer`
     stop in the rescue shell (`touch /tmp/go` continues).
3. **Boot partition** (ext2, label `pmOS_boot`): `/extlinux/extlinux.conf`,
   `/ubuntu/vmlinuz`, `/ubuntu/initramfs`, `/ubuntu/sdm439-xiaomi-olive.dtb`.
4. **Disk image:** an MBR with p1 = boot (512 MiB) and p2 = root (ext4, label
   `pmOS_root`), as an Android sparse image with explicit zero-fill chunks.
   Fresh filesystem UUIDs for every build.
5. **lk2nd** (`image/build-lk2nd.sh`).

It asks for the password of the user it creates; user name, time zone,
locale, keyboard and an SSH key are environment variables (see
`image/common/README.md`). Nothing optional is installed; see `extras/`.

Output in `dist/image/`: `userdata.img`, `lk2nd.img`, `SHA256SUMS`.
