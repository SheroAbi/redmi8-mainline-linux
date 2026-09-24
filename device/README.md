# Device side

`rootfs/` holds every file the port adds to or changes in Ubuntu 24.04,
at its place in the filesystem. It was collected from the running phone by
listing every file that no package owns or whose content differs from its
package.

| File | Purpose |
|---|---|
| `etc/systemd/system/olive-gpu.service`, `usr/local/bin/olive-gpu` | load msm GPU-only, then enable Mesa `kmsro` for the session |
| `etc/systemd/system/olive-wifi-noht.service`, `usr/local/sbin/olive-wifi-noht` | Wi-Fi without 802.11n (TX aggregation loses frames) |
| `etc/systemd/system/olive-autoconfirm.{timer,service}`, `usr/local/bin/olive-confirm-boot` | resets the initramfs boot counter 90 s after a boot |
| `etc/systemd/system/olive-net.service`, `olive-watch.service`, `usr/local/bin/olive-{net,watch}` | keep the USB control link and sshd up |
| `usr/local/bin/olive-report` | one-shot hardware/driver report |
| `etc/systemd/network/20-usb.network` | `usb0`: 172.16.43.1 (not the S9+'s 172.16.42.1) + 169.254.66.1, DHCP server for the PC (no gateway/DNS) |
| `etc/NetworkManager/conf.d/99-olive.conf` | NM leaves `usb0` alone; Wi-Fi power save off |
| `etc/modprobe.d/olive-staged.conf` | modules that must not autoload (msm, LM3697, DSI panel, old touch) |
| `etc/modules-load.d/olive.conf` | USB gadget, i2c-dev |
| `etc/systemd/logind.conf.d/*` | power key and lid ignored by logind, no suspend |
| `etc/systemd/system.conf.d/90-olive-watchdog.conf`, `etc/sysctl.d/90-olive-debug.conf` | watchdog 20 s/30 s, panic on hung task / soft lockup, reboot after 10 s |
| `etc/systemd/zram-generator.conf`, `etc/sysctl.d/90-olive-zram.conf` | zram swap, half of RAM, zstd |
| `etc/systemd/journald.conf.d/persist.conf` | persistent journal, max 200 MB |
| `etc/udev/rules.d/90-olive-hide-android.rules` | Android partitions not shown in Files |
| `etc/dconf/…`, `etc/gdm3/custom.conf` | system GNOME defaults (power key, on-screen keyboard), autologin |
| `etc/apt/…` | Ubuntu ports sources, Mozilla's Firefox repository with its pin |
| `usr/share/gnome-shell/extensions/olive-display@redmi8/` | notch and rounded corners, maximized windows |
| `etc/fstab`, `etc/hostname`, `etc/default/keyboard` | root/boot by UUID, host name `redmi8`, German keyboard layout (change `XKBLAYOUT` for yours) |

`gnome-user-settings.ini` holds the GNOME settings of the image's user:
German keyboard, Yaru dark, on-screen keyboard, no edge tiling, dock favourites
(Firefox, Files, Terminal, Text Editor, Settings) and the extension enabled.
Apply it to another user with `dconf load / < gnome-user-settings.ini`.
