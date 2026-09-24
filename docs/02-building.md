# Building

Five things make up an installed system; each can be rebuilt on its own.

| Piece | Built from | Lands in |
|---|---|---|
| Kernel `vmlinuz` + in-tree modules | msm89x7 `v7.1.3-r1` + `kernel/patches/` + `kernel/config-*` | `/boot/olive-main/vmlinuz`, `/usr/lib/modules/7.1.3-msm89x7-olive-r7/kernel` |
| Out-of-tree drivers | `kernel/modules/` | `/usr/lib/modules/…/extra/*.ko` |
| Device tree | kernel-built DTB + `kernel/devicetree/1..3-*.py` | `/boot/olive-main/sdm439-xiaomi-olive.dtb` |
| Initramfs | postmarketOS mkinitfs + `initramfs/init_2nd.sh` | `/boot/olive-main/initramfs` |
| Flashable image | a running, configured phone | `redmi8-ubuntu-<date>-userdata.img` |

Built artefacts (kernel, initramfs, images) are not part of this repository;
`dist/` is the local place for them and is ignored by git.

## Build host

Any Linux, WSL2 Ubuntu 24.04 included. The reference kernel was built with
clang 18.1.3, `make ARCH=arm64 LLVM=1`. The device-tree edits need Python 3
with the `fdt` package (`pip install fdt`) and run on Windows too.

## 1. Kernel

**Base:** `msm89x7-mainline/linux`, tag `v7.1.3-r1`, as packaged by
postmarketOS (`device/testing/linux-postmarketos-qcom-msm89x7` in pmaports,
tarball `linux-postmarketos-qcom-msm89x7-v7.1.3-r1.tar.gz`, with its patches
0001–0003).

**Patch steps**, in order (`kernel/patches/`, details in its README):

| # | Step | Changes |
|---|---|---|
| 00 | `00-olive-display-touch-v2.patch` | panel node and supplies, generated ILI9881H+ panel driver |
| — | pmaports 0001–0003 | UBWC entry for SDM439, 12 nm DSI PHY DT override (undone by 03), DSI byte-clock OPP |
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

All of it in one go, then the build:

```bash
kernel/patches/apply-all.sh <tree> <dir-with-pmaports-0001-0003>
make -C <tree> ARCH=arm64 LLVM=1 olddefconfig
make -C <tree> ARCH=arm64 LLVM=1 -j$(nproc) Image.gz modules qcom/sdm439-xiaomi-olive.dtb
make -C <tree> ARCH=arm64 LLVM=1 INSTALL_MOD_STRIP=1 INSTALL_MOD_PATH=<stage> modules_install
```

`Image.gz` is installed as `vmlinuz`. `CONFIG_MODULE_SIG` is on but not forced,
so modules from another build of the same version load (they taint the kernel).

> **Honest limit.** The tree that built the reference kernel no longer
> exists. The steps above were reconstructed from the scripts that built it,
> and the in-tree touch driver they start from is the development copy in
> `kernel/patches/src/`. A rebuild gives a functionally equal kernel, not a
> bit-identical one. Please open an issue if a step does not apply.

## 2. Out-of-tree drivers

```bash
scripts/build/build-modules.sh <any configured 7.1.3 msm89x7 tree>
```

The modules only need headers: the running ones were built against an
unpatched worktree of the same version prepared with our config
(`LOCALVERSION=` keeps kbuild from adding `+`). Copy the three `.ko` files to
`/usr/lib/modules/7.1.3-msm89x7-olive-r7/extra/` and run `depmod -a`.

## 3. Device tree

The installed DTB is the kernel-built one plus three edits, applied in order
with Python `fdt` (verified byte-exact against the installed file):

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

`sdm439-xiaomi-olive.kernel-built.dtb` is the input as the reference kernel
built it; `sdm439-xiaomi-olive.dtb` is the result that boots.

## 4. Initramfs

postmarketOS mkinitfs output with one modified file, `initramfs/init_2nd.sh`
(see [`initramfs/README.md`](../initramfs/README.md)):

* early USB NCM + telnet rescue on `169.254.66.1:23` before root discovery,
* a boot counter on the rootfs: three boots without confirmation stop before
  `switch_root` (the USB rescue stays up); `olive-autoconfirm.timer` confirms
  90 s after a boot,
* `olive.test=r7` on the command line arms `olive-r6-safe.conf` as the next
  boot's default before anything risky runs,
* the diagnostic 10 s gate only with `olive.gate` on the command line,
* the kernel modules for early boot.

`scripts/build/initramfs-edit.py` replaces a single file inside the gzip'd
cpio and copies every other entry byte for byte; `--check` proves a
round-trip is identical first. It needs no cpio and runs on Windows.

## 5. The flashable image

The image is made **on a working phone**, from its running system. Copy the
two scripts over (USB network: the phone is `172.16.43.1`) and run them as
root:

```bash
scp scripts/image/make-image.sh scripts/image/verify-image.sh user@172.16.43.1:/var/tmp/
ssh user@172.16.43.1
sudo sh /var/tmp/make-image.sh                         # ~4 min
sudo sh /var/tmp/verify-image.sh /var/tmp/redmi8-image/redmi8-ubuntu-<date>-userdata.img
# then copy the .img, .sha256 and .manifest from /var/tmp/redmi8-image/ to dist/
```

`make-image.sh` copies `/` (one filesystem) and the used part of `/boot`,
removes everything personal — Wi-Fi networks, SSH host keys, every
`authorized_keys`, history, keyrings, caches, logs, apt lists — sets `user`'s
password to `1234`, locks root, and adds `olive-firstboot.service` (new host
keys on the first boot). Anything else that must stay out goes into
`EXTRA_EXCLUDES`. It keeps the filesystem UUIDs, builds ext2/ext4 with
`mke2fs -d` (no loop devices), writes the MBR and converts to an Android
sparse image with explicit zero-fill chunks.

`verify-image.sh` never mounts the image either: a second block device with
the running root's UUID can make systemd unmount the live root. It reads the
filesystems with `e2fsck -n` and `debugfs` and checks 20 points (clean
filesystems, labels, boot files, no keys/Wi-Fi/PSK, password state, firstboot
unit, modules, zap firmware).
