# Performance

Measured on the reference unit in September 2026, GNOME Wayland session
running, phone on USB. Tools: `systemd-analyze`, `/sys` and `/proc` readouts,
`ping` and SFTP from a Windows PC.

## Boot

| | before | after |
|---|---|---|
| Kernel + initramfs | 15.0 s | 5.1 s |
| Userspace to `graphical.target` | 12.2 s | 11.8 s |
| **Total (`systemd-analyze`)** | **27.2 s** | **16.9 s** |

The 10 s were a diagnostic gate in the reference phone's first initramfs,
waiting on every boot for a rescue connection. The initramfs of the clean
image has no such gate.

## Wi-Fi

| | 802.11n (as the driver sets it up) | legacy rates (`olive-wifi-noht`) |
|---|---|---|
| Ping loss, PC → phone | 50–80 % | **0 %** |
| Round trip | 15–50 ms | **1–2 ms** |
| SSH login | often times out | < 0.5 s |
| SFTP PC → phone | stalls | 2.3 MB/s |
| SFTP phone → PC | stalls | 1.3 MB/s |

Signal −52 dBm, 2.4 GHz channel 11.

## CPU, GPU, memory, thermals (idle desktop)

| | |
|---|---|
| CPU clusters | cpu0,5–7 up to 1.96 GHz; cpu1–4 up to 1.46 GHz; `schedutil` |
| Load average | 0.1 |
| `gnome-shell` | 0.7 % CPU, 260 MB RSS |
| GPU (devfreq `simple_ondemand`) | 19.2 MHz idle, 450 MHz under load |
| RAM | 700 MB of 3.6 GB used, 3.0 GB available |
| Swap | 1.8 GB zram, zstd, `vm.swappiness=150` |
| Temperatures | 36–38 °C (CPU, GPU, PMIC) |
| Storage | eMMC, `mq-deadline`, loop device with direct I/O |
| Failed units | none |

## What would still make it faster

* **CPU idle states** — there is no cpuidle driver (`current_driver: none`),
  so idle cores never power down. Costs battery, not speed.
* **Wi-Fi at HT rates** — a wcn36xx fix instead of the legacy-rate
  workaround would roughly double throughput.
* **Native display pipeline** — with msm driving the panel the GPU could scan
  out directly; today every frame is copied into the bootloader's framebuffer.
  At 720x1520 that copy is cheap (gnome-shell idles at 0.7 %), but it also
  means no real display power-off.
