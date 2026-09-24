# Initramfs

The initramfs is postmarketOS `mkinitfs` output for this device with one
modified file, `init_2nd.sh`, which is kept here exactly as it runs.

What the changes do:

* **USB rescue before root discovery.** The USB NCM gadget comes up first and
  a telnet shell listens on `169.254.66.1:23` (USB only, never Wi-Fi).
* **Boot counter.** Every boot increments `/var/lib/olive/bootcount` on the
  root filesystem. After three boots that were never confirmed, the initramfs
  stops before `switch_root` and keeps the rescue shell up.
  `olive-autoconfirm.timer` in the running system resets the counter 90 s after
  a boot. In the rescue shell, `touch /tmp/go` continues a stopped boot.
* **Test-kernel rollback.** With `olive.test=r7` on the kernel command line the
  initramfs makes `olive-r6-safe.conf` the default extlinux entry *before*
  anything risky runs, so any reset afterwards comes back on the safe entry.
* **Optional diagnostic gate.** Only with `olive.gate` on the command line, it
  waits 10 s for a rescue connection after mounting root.

To put a changed `init_2nd.sh` into an existing initramfs without cpio (works
on Windows too):

```bash
python scripts/build/initramfs-edit.py initramfs initramfs.new --check
python scripts/build/initramfs-edit.py initramfs initramfs.new --replace init_2nd.sh initramfs/init_2nd.sh
```
