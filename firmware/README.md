# Firmware

Installed in the image under `/usr/lib/firmware/`; kept here so the port can
be rebuilt without a stock ROM at hand.

| File | Needed by | Source |
|---|---|---|
| `qcom/sdm439/xiaomi/olive/a506_zap.{mdt,b00,b01,b02}` | Adreno 505 (zap shader through TrustZone) | stock `vendor` partition, `/vendor/firmware/a506_zap.*` |
| `ilitek/olive-ili9881h-c3i-0x04.ili` | `ili9881h-tddi-fb` (touch RAM firmware, C3I/Tianma panel) | vendor kernel `C3I_TIANMA_6217_LongH_V0x04.ili` (a text array of hex bytes), converted byte for byte with `convert-touch-firmware.py` |

Everything else comes from the phone itself at boot (`msm-firmware-loader`):
Wi-Fi (`wcnss.*`) and its per-unit calibration `WCNSS_qcom_wlan_nv.bin` from
`persist`, ADSP from `modem`, venus from `vendor`.
