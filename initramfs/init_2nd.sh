#!/bin/busybox ash
# shellcheck disable=SC1091

# This is the "real" init.sh script, it's either jumped to immediately
# from init.sh, or loaded from initramfs-extra on the boot partition
# on space constrained devices with deviceinfo_create_initfs_extra="true".

# The set -a in init.sh only exports variables, not functions
. /init_functions.sh
. /init_functions_2nd.sh

# Handle halt/poweroff/reboot
# Signals from busybox/halt.c
trap 'halt -f' USR1
trap 'poweroff -f' USR2
trap 'reboot -f' TERM

# Run udev early, before splash, to make sure any relevant display drivers are
# loaded in time
modprobe libcomposite
modprobe usb_f_ncm
setup_usb_network
ip link set usb0 up
ip addr add 172.16.42.1/24 dev usb0 2>/dev/null || true
ip addr add 169.254.66.1/16 dev usb0 2>/dev/null || true
# The emergency shell is reachable on the USB link only, never on Wi-Fi.
telnetd -b 169.254.66.1:23 -l /bin/sh
echo "OLIVE: early USB rescue ready, before root discovery" > /dev/kmsg
setup_udev

# Start splash
if [ "$nosplash" != "y" ] && [ "$IN_CI" = "false" ]; then
	setup_framebuffer
	splash_start
	splash_set_message "Loading"
fi

setup_dynamic_partitions "${deviceinfo_super_partitions:=}"

run_hooks /hooks

if [ "$debug_shell" = "y" ]; then
	debug_shell
fi

check_keys

# If running from initramfs-extra this will be a no-op since it was
# called before to mount the boot partition
mount_subpartitions

# A diagnostic boot arms the known-good kernel for the NEXT reset before drivers
# or userspace are tested. Current kernel and modules remain r7 for this boot.
if grep -q 'olive.test=r7' /proc/cmdline; then
    mkdir -p /olive-boot
    wait_boot_partition
    if ! mount_boot_partition /olive-boot rw; then
        echo "OLIVE: rollback mount failed; staying in USB rescue" > /dev/kmsg
        while :; do sleep 1; done
    fi
    if [ ! -s /olive-boot/extlinux/olive-r6-safe.conf ] ||
       ! cp /olive-boot/extlinux/olive-r6-safe.conf /olive-boot/extlinux/extlinux.conf.next ||
       ! sync -f /olive-boot ||
       ! mv /olive-boot/extlinux/extlinux.conf.next /olive-boot/extlinux/extlinux.conf ||
       ! sync -f /olive-boot; then
        echo "OLIVE: rollback not durable; staying in USB rescue" > /dev/kmsg
        while :; do sleep 1; done
    fi
    umount /olive-boot
    echo "OLIVE: r6 rollback armed for next reset" > /dev/kmsg
fi

run_hooks /hooks-extra

wait_root_partition
delete_old_install_partition
resize_root_partition
unlock_root_partition
resize_root_filesystem
mount_root_partition
resize_filesystem_after_mount /sysroot

# Mount boot partition into sysroot if needed since some
# old installations don't have a proper /etc/fstab file. See #2800
if [ -z "$(cat /sysroot/etc/fstab | grep -v "#" | tr -d '[:space:]')" ]; then
	wait_boot_partition
	mount_boot_partition /sysroot/boot "rw"
fi

# The 10 s diagnostic gate (telnet on 169.254.66.1:23, `touch /tmp/go`) only
# when asked for with olive.gate on the kernel command line; it used to cost
# every boot 10 s.
_gate=0
grep -q 'olive.gate' /proc/cmdline && _gate=10
echo "OLIVE: root mounted; diagnostic gate $_gate s" > /dev/kmsg
_i=0
while [ "$_i" -lt "$_gate" ] && [ ! -e /tmp/go ]; do
    sleep 1
    _i=$((_i + 1))
done
init="/sbin/init"
setup_bootchart2

# Switch root
run_hooks /hooks-cleanup

echo "Switching root"

# Restore stdout and stderr to their original values if they
# were stashed
if [ -e "/proc/1/fd/3" ]; then
	exec 1>&3 2>&4
elif [ "$debug_shell" != "y" ]; then
	echo "$LOG_PREFIX Disabling console output again (use 'pmos.debug-shell' to keep it enabled)"
	exec >/dev/null 2>&1
fi

# Make it clear that we're at the end of the initramfs
splash_set_message "Starting"

# Re-enable kmsg ratelimiting (might have been disabled for logging)
echo ratelimit > /proc/sys/kernel/printk_devkmsg

# Vibrate to indicate that we are booting
if [ "$IN_CI" != "true" ]; then
	beebzzr &
fi

killall udevd syslogd unudhcpd 2>/dev/null

# Kill any getty shells that might be running
for pid in $(pidof sh); do
	if ! [ "$pid" = "1" ]; then
		kill -9 "$pid"
	fi
done

# cleanup after ourselves
# switch_root does a mount --move , keeping stale filesystems like devtmpfs
# with /dev/log in there.
rm /dev/log 2>/dev/null || true

# shellcheck disable=SC2093

# A failed userspace boot must not permanently remove the early USB rescue path.
_state=/sysroot/var/lib/olive
mkdir -p "$_state"
_count=$(cat "$_state/bootcount" 2>/dev/null)
case "$_count" in ''|*[!0-9]*) _count=0 ;; esac
_count=$((_count + 1))
echo "$_count" > "$_state/bootcount"
sync -f /sysroot
if [ "$_count" -ge 3 ]; then
    echo "OLIVE: three boots without SSH confirmation; USB rescue remains active" > /dev/kmsg
    while [ ! -e /tmp/go ]; do sleep 1; done
fi
echo "OLIVE: userspace handoff; USB gadget retained" > /dev/kmsg
killall telnetd 2>/dev/null || true
exec switch_root /sysroot "$init"

echo "$LOG_PREFIX ERROR: switch_root failed!" > /dev/kmsg
echo "$LOG_PREFIX Looping forever. Install and use the debug-shell hook to debug this." > /dev/kmsg
echo "$LOG_PREFIX For more information, see <https://postmarketos.org/debug-shell>" > /dev/kmsg
fail_halt_boot
