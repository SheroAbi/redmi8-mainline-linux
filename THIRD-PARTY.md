# Third-party components

| Path | Origin | Terms |
|---|---|---|
| `firmware/qcom/sdm439/xiaomi/olive/a506_zap.*` | Adreno zap shader from the stock `vendor` partition (MIUI 12, `/vendor/firmware/a506_zap.*`) | Qualcomm proprietary, redistributed as found on the device |
| `firmware/ilitek/olive-ili9881h-c3i-0x04.ili` | ILITEK ILI9881H touch RAM firmware for the C3I/Tianma panel, converted from the vendor kernel's `C3I_TIANMA_6217_LongH_V0x04.ili` | ILITEK proprietary |
| `kernel/downstream-reference/` | Xiaomi/LineageOS `android_kernel_xiaomi_sdm439` (4.9) and the stock device tree, for reference only | GPL-2.0 (sources), device tree as published by Xiaomi |
| `kernel/patches/sdm439-12nm/` | `dsi_phy_12nm.c` and neighbours from the linux-msm tree at `ce300c988d76` | GPL-2.0-only |
| `kernel/patches/src/ili9881h-tddi.c`, `kernel/modules/ili9881h-tddi-fb.c`, `ili9881h-ram-loader.h` | written for this port; the wire protocol follows ILITEK's GPL-2.0 vendor driver (`drivers/input/touchscreen/ili9881h/`, © 2011 ILI Technology Corp.) | GPL-2.0-only |
| `kernel/patches/00-olive-display-touch-v2.patch` | postmarketOS `89x7-mainline` device work, extended | GPL-2.0-only |
| lk2nd (built by `image/build-lk2nd.sh`, not in this repository) | https://github.com/msm8916-mainline/lk2nd @ `8b46487c` (2026-09-20) | BSD-3-Clause / MIT (LK) |
| msm-firmware-loader 1.8.0 (downloaded by the image build) | https://gitlab.postmarketos.org/postmarketOS/msm-firmware-loader | MIT |
| `kernel/patches/0001-soc-qcom-ubwc-add-sdm439.patch` | a one-line addition to `drivers/soc/qcom/ubwc_config.c` of the msm89x7 tree | GPL-2.0-only |
| `wcnss.*` Wi-Fi firmware and `qcom/a530_*` GPU microcode on the phone | linked at boot from the stock `modem`/`vendor` partitions, and Ubuntu's `linux-firmware` | Qualcomm proprietary |
| Wi-Fi calibration (`WCNSS_qcom_wlan_nv.bin`), ADSP, venus | not shipped: `msm-firmware-loader` links them at boot from the phone's own `persist`, `modem` and `vendor` partitions — the NV file is calibrated per phone | — |

The Ubuntu userland the image build installs comes from the Ubuntu 24.04 archive and Mozilla's Firefox APT repository, under their own licences.
