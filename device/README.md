# Device layer

What the Redmi 8's image carries on top of the common base system
([`../image/common/README.md`](../image/common/README.md)): only what this
phone's hardware needs. `image/build-image.sh` copies `base/` into the image,
installs `packages.txt` and runs `configure.sh` inside it.

| File | Purpose |
|---|---|
| `base/etc/initramfs-tools/` | the initramfs hooks: USB rescue shell, the userdata disk image as a loop device, the boot counter |
| `base/etc/systemd/system/olive-gpu.service`, `base/usr/local/bin/olive-gpu` | load msm GPU-only, then enable Mesa `kmsro` for the session |
| `base/etc/systemd/system/olive-wifi-noht.service`, `base/usr/local/sbin/olive-wifi-noht` | Wi-Fi without 802.11n (TX aggregation loses frames) |
| `base/etc/systemd/system/olive-autoconfirm.{timer,service}`, `base/usr/local/bin/olive-confirm-boot` | reset the initramfs boot counter 90 s after a boot |
| `base/etc/systemd/system/olive-net.service`, `olive-watch.service`, `base/usr/local/bin/olive-{net,watch}` | keep the USB link and SSH up |
| `base/etc/systemd/system/msm-firmware-loader.service.d/` | the loader's run directory (the loader itself is downloaded by the build) |
| `base/etc/systemd/network/20-usb.network` | `usb0`: 172.16.43.1 + 169.254.66.1, DHCP server for the PC (no gateway/DNS) |
| `base/etc/NetworkManager/conf.d/99-olive.conf` | NM leaves `usb0` alone; Wi-Fi power save off |
| `base/etc/modprobe.d/olive-staged.conf` | modules that must not autoload (msm, LM3697, DSI panel, old touch) |
| `base/etc/modules-load.d/olive.conf` | USB gadget, i2c-dev |
| `base/etc/systemd/logind.conf.d/*` | power key and lid ignored by logind, no suspend |
| `base/etc/systemd/system.conf.d/90-olive-watchdog.conf`, `base/etc/sysctl.d/90-olive-debug.conf` | watchdog 20 s/30 s, panic on hung task / soft lockup, reboot after 10 s |
| `base/etc/udev/rules.d/90-olive-hide-android.rules` | Android partitions not shown in Files |
| `base/etc/dconf/db/local.d/50-olive` | GNOME: power button does nothing, no automatic sleep |

Optional features live in [`../extras/`](../extras/).
