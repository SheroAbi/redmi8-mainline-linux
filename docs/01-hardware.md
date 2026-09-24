# Hardware

Everything below was read on the device (registers over `/dev/mem` and
i2c-dev, the stock device tree in `kernel/downstream-reference/`), not taken
from a datasheet.

## Boot chain

```
Stock Xiaomi lk (aboot, unlocked)     fastboot 18d1:d00d, product=olive, kernel=lk
   |  Volume-Down + Power -> this fastboot, always (it lives in aboot, not in boot)
   v  loads the `boot` partition (64 MiB)
lk2nd (320 KiB Android boot image)     fastboot 18d1:d001, kernel=lk2nd
   v  reads /extlinux/extlinux.conf from userdata, sub-partition 1
vmlinuz + initramfs + DTB (fdtdir)
   v  initramfs (Ubuntu initramfs-tools + this port's hooks): USB rescue, attaches the disk image
switch_root -> Ubuntu 24.04 on userdata, sub-partition 2
```

`userdata` (`mmcblk0p62`, 50 GB) holds a whole disk image with its own MBR:

| | start (sectors) | size | fs | label |
|---|---|---|---|---|
| p1 | 2048 | 512 MiB | ext2 | `pmOS_boot` |
| p2 | 1050624 | rest | ext4 | `pmOS_root` |

The filesystem UUIDs are new for every image build. The initramfs attaches
the image as a loop device with partitions (`/dev/loop0p1`, `/dev/loop0p2`);
on the first boot `grow-rootfs.service` grows p2 and its filesystem to the
end of `userdata`.

Android's own partitions (`modem`, `persist`, `vendor`, `dsp`, …) stay as they
are; `msm-firmware-loader` mounts them read-only at boot and links their
firmware into `/run/msm-firmware-loader/target` (the kernel's
`firmware_class.path`).

## Buses and chips

| Function | Chip | Where | Notes |
|---|---|---|---|
| Backlight | **KTD3137** | I²C controller @0x7af5000, address 0x36, ID register 0x00 = 0x18 | Redmi 8 units carry either an LM3697 or a KTD3137 at this address. This unit has the KTD3137; the LM3697 driver resets it and the screen goes dark. |
| Panel | ILITEK ILI9881H (`ili9881h_hdplus_video_c3i`) | DSI0, 12 nm PHY | video mode, 720x1520 |
| Touch | ILITEK TDDI (same IC) | SPI controller @0x78b7000, IRQ gpio65, reset gpio64 | scans only while the panel shows a picture |
| Charger | PMI632 SMB5 | SPMI 0x1000 | float voltage and current limit set by the bootloader |
| Fuel gauge | PMI632 QG | SPMI 0x4800 | `QG_LAST_ADC_V` 0xc0, `QG_LAST_ADC_I` 0xc2; the averaged register reads 0x8000 = invalid |
| GPU | Adreno 505 (chip id 5.0.5) | 0x1c00000 | needs the zap shader (`a506_zap`, TZ PAS id 13) |
| Wi-Fi / BT | pronto v3 + IRIS (DT: `qcom,wcn3620`) | 0xa204000 | 5-wire pins gpio76-80, 19.2 MHz XO; calibration in `persist` |
| USB | ChipIdea, peripheral | | configfs gadget: NCM (`usb0`) |
| Keys | pm8941 pwrkey/resin, gpio-keys | | all three keys work |

Useful register facts, measured:

* GPU clock: GPLL3 has a 4-bit post-divider. With width 0 (the tree's
  default) the GPU ran at 700 MHz instead of 450 MHz.
* A505 reports the same feature word as the A506 in the stock kernel (0x660,
  including CPZ retention), so it must not call the zap *resume* SCM.
* KTD3137: MODE 0x02 = 0x99, CONTROL 0x03 = 0x6e, PWM 0x06 = 0x1b (as the bootloader leaves them);
  brightness is 11 bit, LSB 0x04 bits [2:0], MSB 0x05 bits [10:3].
* SMB5 `BATTERY_CHARGER_STATUS_1` (0x1006): 0 and 5 = full/terminated,
  1–4 = charging. `POWER_PATH_STATUS` 0x110b, ICL status 0x1107, APSD
  result 0x1307/0x1308.

## What differs between Redmi 8 units

Xiaomi built the olive with several panel and backlight suppliers. This port
supports exactly one combination:

| Part | Supported | Also exists (not supported) |
|---|---|---|
| Panel/touch | ILI9881H C3I (Tianma), touch firmware `0x04` | other ILI9881H vendors, other panel ICs |
| Backlight | KTD3137 | LM3697 (the DTB would need the `ti,lm3697` node back) |

The stock boot log (`dmesg` of MIUI or `cat /proc/cmdline` there) names the
panel as `mdss_dsi_ili9881h_hdplus_video_c3i`. On another combination the
display still works (it is the bootloader's framebuffer), touch and
brightness do not.

The Wi-Fi calibration file is per unit and is **not** in the image; it is
linked from the phone's own `persist` partition at boot.

The reference unit: bootloader unlocked, eMMC 61.3 GiB, A-only partition
layout. Take a full partition backup of your own unit before you flash
anything.
