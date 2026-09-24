# Kernel patch steps

The Redmi 8 kernel is `msm89x7-mainline/linux` tag `v7.1.3-r1` plus the steps
below. `scripts/build/build-kernel.sh` clones the tag and runs them; by hand:

```bash
git clone --depth 1 --branch v7.1.3-r1 https://github.com/msm89x7-mainline/linux
kernel/patches/apply-all.sh linux
```

Most steps are Python scripts that edit the tree in place and `assert` on the
text they expect, so a step applied to the wrong tree, or twice, fails loudly
instead of half-applying. Each takes the kernel tree as its only argument.

| Step | Change |
|---|---|
| `00-olive-display-touch-v2.patch` | panel node and supplies, generated ILI9881H+ panel driver (postmarketOS `89x7-mainline` device work, extended) |
| `0001-soc-qcom-ubwc-add-sdm439.patch` | UBWC entry for the SDM439 (`msm8937_data`), recovered from the reference kernel's `ubwc_config.ko` |
| `01-dts-touch-backlight-gpu.py` | touch SPI node, LM3697 backlight wiring, `&gpu` enabled |
| `02-add-touch-driver.py` | in-tree `ili9881h-tddi` touch driver from `src/` + Kconfig/Makefile |
| `03-port-dsi-phy-12nm.py` | `dsi_phy_12nm.c` from `sdm439-12nm/` (linux-msm experiment `ce300c988d76`) ported to 7.1, PHY registration, DT PHY timings, SPI mode 0, `LOCALVERSION=-msm89x7-olive-r7` |
| `04-fix-dsi-pll-rate.py` | 12 nm PLL: fractional (SSC) `recalc_rate`; touch TX timeout message |
| `05-touch-ram-firmware.py` | touch: RAM firmware at probe + demo mode, coordinate clamp (uses `../modules/ili9881h-ram-loader.h`) |
| `06-touch-panel-follower.py` | touch as DRM panel follower, `olive_panel` label; a5xx `TRAP_LOG_HI << 32` |
| `07-touch-firmware-query.py` | firmware query (0x22/0x21) before the IRQ is enabled |
| `08-fix-dsi-phy-range.py` | `dsi_12nm_sync_phy_range()`: signal range follows the final divider |
| `09-fix-gpll3-width.py` | GPLL3 `.width = 4` in `gcc-msm8917.c` — GPU at 450 MHz, not 700 |
| `10-gpu-zap-a505.py` | A505 skips zap *resume* (it reset the SoC); DT `zap-shader`, `gpu_zap_mem`, ramoops |

`sdm439-12nm/` holds the reference sources step 03 ports from. The in-tree
touch driver (steps 02–07) waits for a DSI panel; the running system uses the
out-of-tree `../modules/ili9881h-tddi-fb.c` instead, which is the same driver
without the panel dependency. Both are built, only the `-fb` one is loaded.

The KTD3137 backlight is not an in-tree patch: the running system uses the
out-of-tree `ktd3137-backlight` module and a device-tree edit
(`../devicetree/1-dtb-ktd3137.py`).
