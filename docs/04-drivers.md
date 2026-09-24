# Drivers and fixes

Each entry says what was wrong, how it showed, and what fixed it. The order
is the order in which they were found; each one hid the next.

## GPU (Adreno 505)

Three independent faults, all in `kernel/patches/`:

1. **Everything rendered as zeros.** Command-processor writes worked, but
   anything through UCHE — clears, shaders, compute — vanished without an
   error. Stock loads the zap shader `a506_zap` through TrustZone (PAS id 13);
   mainline did not for this board. Fix: DT `zap-shader` node with
   `gpu_zap_mem` and the firmware at
   `/lib/firmware/qcom/sdm439/xiaomi/olive/a506_zap.*` (from the stock
   `vendor` partition, also linked by msm-firmware-loader).
2. **Hard SoC reset when the GPU woke up.** Mainline calls the zap *resume*
   SCM for A505. In the stock kernel the A505 carries the A506 feature word
   (0x660, with CPZ retention): the secure world keeps the zap state and the
   resume call resets the SoC. Fix: `a5xx_zap_shader_resume` returns early for
   A505 (`10-gpu-zap-a505.py`). Five GPU runtime suspend/resume cycles clean afterwards.
3. **GPU at 700 MHz instead of 450.** GPLL3's post-divider was declared with
   width 0, so the divider was ignored. Fix: width 4 in `gcc-msm8917.c`
   (`09-fix-gpll3-width.py`); measured 450 MHz.

### How GNOME uses it

The msm display pipeline does not bring the panel up (see known issues), so
msm is loaded **GPU-only**: the MDSS node is disabled in the DT and
`olive-gpu.service` runs `modprobe msm separate_gpu_kms=1`. msm then offers
a render node (`/dev/dri/renderD128`) and no display. Only when that node is
there does the service write `MESA_LOADER_DRIVER_OVERRIDE=kmsro` to
`/run/environment.d/`: Mesa renders with freedreno and shares buffers with the
display device, which is `simpledrm` on the bootloader's framebuffer. If msm
fails to load, nothing is written and GNOME falls back to software rendering
instead of a black screen.

`msm` is blacklisted for autoloading (`/etc/modprobe.d/olive-staged.conf`)
and must never be unloaded: `rmmod msm` crashes the kernel.

## Backlight: `ktd3137-backlight` (own)

The olive is built with either a TI LM3697 or a Kinetic KTD3137 at I²C 0x36.
The DT said LM3697; this unit has the KTD3137 (ID register 0x00 = 0x18). The
LM3697 driver's reset sequence switched the KTD3137 off: black screen, while
everything else worked.

The driver checks the ID, keeps the bootloader's MODE/CONTROL/PWM values
(0x99/0x6e/0x1b), exposes an 11-bit `backlight` device (0–2047, LSB 0x04
bits [2:0], MSB 0x05) and turns the LED current off for `bl_power` ≠ 0. GNOME's
brightness slider and the power key's display-off use it.

## Touch: `ili9881h-tddi-fb` (own)

The touch controller is part of the display driver IC and only scans while
the panel is fed video. The in-tree `ili9881h-tddi` (patch steps 02/05/06)
is written as a DRM *panel follower* and waits for a DSI panel that never
comes up. `ili9881h-tddi-fb` is the same driver without the follower: it
loads the RAM firmware (`ilitek/olive-ili9881h-c3i-0x04.ili`) at probe,
enables the IRQ and reports 10-finger multitouch. Because the bootloader's framebuffer keeps the panel running,
the touch works. The DT's touch → panel link is removed
(`2-dtb-fbmode.py`), otherwise the device link would defer the probe forever.

## Battery and charger: `olive-power` (own, read-only)

Mainline has no PMI632 charger/gauge driver. `olive-power` registers two
power supplies from the SPMI registers and **writes nothing**:

* `usb`: online (POWER_PATH_STATUS), input current limit (ICL_STATUS), USB
  type from APSD (SDP/CDP/DCP/float).
* `battery`: status from SMB5 `BATTERY_CHARGER_STATUS_1` (0/5 = full,
  1–4 = charging), voltage and current from `QG_LAST_ADC_V/I` (the averaged
  `QG_S2_AVG` registers read 0x8000 = no data and are rejected), capacity
  seeded from the open-circuit voltage and then coulomb-counted, scaled to the
  4.20 V float voltage the bootloader set (4.20 V = 100 %), `Full` = 100 %.

It polls every 5 s. UPower shows the battery icon, percentage and the
charger state.

## Wi-Fi: `olive-wifi-noht` (workaround)

wcn36xx associates with 802.11n and immediately sets up a TX Block-Ack
session (A-MPDU) with the access point. From then on the phone receives
everything but 50–80 % of what it sends never arrives, and what arrives is
15–50 ms late: pings, TCP ACKs, SSH logins. Measured by counting ICMP echo
requests in and replies out on the phone (all answered) against replies seen
on the PC. Not the calibration (identical to `persist`), not the 5-wire pins
(identical to stock), not Bluetooth coexistence, not RTS/CTS; TX-rate masks
and TX power are not supported by the driver.

Associating **without HT** fixes it: 0 % loss, 1–2 ms. `olive-wifi-noht` is a
`wpa_cli` action script (`olive-wifi-noht.service`): on every CONNECTED event
it sets `disable_ht 1` for the current network and reassociates, and it looks
once at start-up because the phone often connects before it listens.
NetworkManager keeps the connection through the reassociation.

The real fix belongs in wcn36xx (no TX aggregation, or a correct sequence
number handover to the firmware); with it the link would run at HT rates.

## Initramfs rescue

See [02-building.md](02-building.md#4-initramfs): USB rescue shell before
root discovery, boot counter with automatic confirmation after 90 s,
`olive.test=r7` rollback, optional diagnostic gate.

## Desktop integration

* `olive-display@redmi8` GNOME extension: moves the clock to the left so
  nothing sits under the notch, pads the top bar 34 px on both sides for the
  rounded corners, and maximizes normal windows on their first frame.
* logind ignores a short press of the power key (no suspend, which the phone
  cannot resume from); a long press powers off.
* `/etc/udev/rules.d/90-olive-hide-android.rules` hides the ~60 Android
  partitions from the file manager.
* systemd watchdog (20 s runtime, 30 s reboot) and hung-task/softlockup
  panics with `panic=10`, so a hang ends in a reboot, not a frozen phone.
