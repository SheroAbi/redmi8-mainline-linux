#!/bin/bash
# Redmi 8: hardware configuration, run inside the image during the build
# (image/build-image.sh). Only what this phone needs to work; the optional
# features are in extras/.
set -euo pipefail

# Firmware from the phone's own Android partitions (Wi-Fi calibration,
# wcnss, ADSP, venus), linked at every boot before udev.
systemctl enable msm-firmware-loader.service

# GPU (msm GPU-only + Mesa kmsro), Wi-Fi without 802.11n TX aggregation,
# the USB control link (systemd-networkd serves DHCP on usb0), and the
# confirmation that resets the initramfs boot counter.
systemctl enable olive-gpu.service olive-wifi-noht.service olive-net.service \
	olive-watch.service olive-autoconfirm.timer systemd-networkd.service

# Suspend never resumes on this port.
systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target \
	suspend-then-hibernate.target

dconf update
