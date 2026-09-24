# debug-tools

A one-shot hardware report and a persistent journal, for debugging the port.

    sudo extras/install.sh debug-tools
    sudo olive-report

* `olive-report` prints the kernel command line, the initramfs boot counter,
  loaded display/GPU/touch/Wi-Fi modules, DRM, backlight, input, power supply,
  IIO and SPI devices, network state, failed units and the relevant kernel
  messages, in one go.
* `/etc/systemd/journald.conf.d/persist.conf` keeps the journal across
  reboots (at most 200 MB), so the log of a boot that hung can be read later.
