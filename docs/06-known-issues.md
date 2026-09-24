# Known issues

## Display pipeline (msm DSI) does not drive the panel

With msm's display side enabled the panel gets no commands: no picture, and
without the panel's init sequence no PWM either, so the backlight stays dark.
The 12 nm DSI PHY is ported (`03-port-dsi-phy-12nm.py`, `04`, `08`) and its PLL
locks; where the link fails is not found yet. Next step: a DCS read of 0x0A
from a small module to see whether the link carries anything at all.

Consequences today: the picture is the bootloader's framebuffer; "display
off" turns the backlight off but the panel keeps running; no brightness
control on other backlight variants; touch depends on the running panel.

## Wi-Fi: 802.11n TX aggregation loses frames

See [04-drivers.md](04-drivers.md#wi-fi-olive-wifi-noht-workaround). Worked
around by associating without HT, which caps throughput at legacy rates
(~1–2 MB/s measured). A driver fix would lift it.

The router announced a channel switch with an operating class wcn36xx cannot
parse (`cannot understand ECSA IE operating class, 4, ignoring`); harmless
here, but a real channel change would not be followed.

## Battery temperature

ADC channel 0x4a (battery thermistor) answers `EINVAL`; the thermal zone
`battery` disables itself at boot. UPower shows no temperature. Charging is
not affected (the charger's own protection runs in hardware).

## Charging is what the bootloader set

`olive-power` only reads. Float voltage 4.20 V (stock would charge to
4.40 V), fast charge 2 A, on a PC port 500 mA. 4.20 V is shown as 100 %.
Gentle on the battery, ~10 % less runtime per charge.

## No CPU idle states

No cpuidle driver is bound, idle cores only execute WFI. Battery life is
worse than it could be. The S9+ port shows how this can go wrong (boot hangs
with deep idle); it needs its own careful round.

## Hardware not brought up

Camera, audio, modem (calls, SMS, mobile data), sensors, GPS, fingerprint,
FM radio, Bluetooth pairing (the `hci0` device exists, untested). The
vibration motor has its kernel driver (`pm8xxx_vib`) but nothing uses it.

## Only one hardware variant

ILI9881H C3I panel + KTD3137 backlight. See [01-hardware.md](01-hardware.md).

## Kernel source reconstruction

The tree that built `7.1.3-msm89x7-olive-r7` no longer exists. The source is
the ordered patch steps in `kernel/patches/` on top of msm89x7 `v7.1.3-r1`
and pmaports' patches 0001–0003; a rebuild is functionally equal, not
bit-identical. See [02-building.md](02-building.md#1-kernel).

## USB network drops for a few seconds under load

During a large transfer the NCM link occasionally resets; Windows reports the
network as unreachable for ~10 s, then it is back. Retry long copies.

## Package updates

The reference image is Ubuntu 24.04 with about 325 updates deliberately held
back (GNOME and Mesa changes untested). `apt upgrade` is expected to work; the
kernel is not an Ubuntu package and stays as it is.

## Never

* `rmmod msm` — crashes the kernel.
* Two people or tools changing the phone's system at the same time — builds,
  installs and reboots interleave and leave a state nobody can reason about.
