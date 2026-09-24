#!/usr/bin/env python3
"""First setup of a freshly flashed Redmi 8, over the USB cable.

    python scripts/install/personalize.py --password NEW [--wifi SSID] [--root-key KEY.pub]

The image ships with user "user", password 1234, root locked. This logs in
over USB (172.16.43.1) with that password and

  --password NEW      sets a new password for "user" (do this)
  --wifi SSID         joins a Wi-Fi network; the passphrase is asked for
                      (or taken from WIFI_PSK) and never appears on a command line
  --root-key KEY.pub  lets root log in with that SSH key

Needs Python 3 with paramiko (pip install paramiko).
"""
import argparse
import getpass
import os
from pathlib import Path
import shlex
import sys
import uuid

import paramiko

# 172.16.43.1 is the running system; older images used 172.16.42.1, and
# 169.254.66.1 is the initramfs rescue address.
HOSTS = ('172.16.43.1', '172.16.42.1', '169.254.66.1')


def connect(password):
    last = None
    for host in HOSTS:
        client = paramiko.SSHClient()
        # A new image makes new host keys on its first boot; over the cable
        # the phone is the one in your hand.
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(host, username='user', password=password, timeout=8,
                           look_for_keys=False, allow_agent=False)
            return client, host
        except Exception as error:  # noqa: BLE001 - try the next address
            last = error
            client.close()
    raise SystemExit(f'Redmi 8 not reachable over USB ({", ".join(HOSTS)}): {last}')


def sudo(client, password, command, stdin=b''):
    """Run as root through sudo; the password goes in on stdin, first line."""
    chan = client.get_transport().open_session()
    # -k: always ask, so the first stdin line is never mistaken for input
    # when sudo still has a cached credential from the previous call.
    chan.exec_command('sudo -k -S -p "" sh -c ' + shlex.quote(command))
    chan.sendall(password.encode() + b'\n' + stdin)
    chan.shutdown_write()
    out = b''
    while True:
        data = chan.recv(65536)
        if not data:
            break
        out += data
    err = chan.recv_stderr(65536)
    status = chan.recv_exit_status()
    if status:
        raise SystemExit(f'failed ({status}): {command.split()[0]}\n{(out + err).decode(errors="replace")}')
    return out.decode(errors='replace')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--current', default='1234', help='current password of "user" (image default 1234)')
    p.add_argument('--password', help='new password for "user"')
    p.add_argument('--wifi', metavar='SSID')
    p.add_argument('--root-key', type=Path, metavar='KEY.pub')
    args = p.parse_args()

    client, host = connect(args.current)
    key = client.get_transport().get_remote_server_key()
    print(f'connected to {host}, host key {key.get_name()} {key.get_fingerprint().hex()}')
    try:
        print(sudo(client, args.current, 'cat /etc/olive-build; uname -r').strip())
        if args.root_key:
            line = args.root_key.read_text().strip()
            if not line.startswith(('ssh-ed25519 ', 'ssh-rsa ', 'ecdsa-')):
                raise SystemExit(f'{args.root_key} does not look like a public key')
            sudo(client, args.current,
                 'install -d -m 700 /root/.ssh && touch /root/.ssh/authorized_keys && '
                 'chmod 600 /root/.ssh/authorized_keys && '
                 'k=$(cat) && (grep -qxF "$k" /root/.ssh/authorized_keys || echo "$k" >> /root/.ssh/authorized_keys)',
                 line.encode() + b'\n')
            print('root key installed')
        if args.wifi:
            psk = os.environ.get('WIFI_PSK') or getpass.getpass(f'Passphrase for "{args.wifi}": ')
            name = 'wifi-' + ''.join(c for c in args.wifi if c.isalnum() or c in '-_')[:24]
            profile = (f'[connection]\nid={args.wifi}\nuuid={uuid.uuid4()}\ntype=wifi\nautoconnect=true\n\n'
                       f'[wifi]\nmode=infrastructure\nssid={args.wifi}\n\n'
                       f'[wifi-security]\nkey-mgmt=wpa-psk\npsk={psk}\n\n'
                       '[ipv4]\nmethod=auto\n\n[ipv6]\nmethod=auto\naddr-gen-mode=default\n')
            path = f'/etc/NetworkManager/system-connections/{name}.nmconnection'
            sudo(client, args.current,
                 f'umask 077 && cat > {path} && chmod 600 {path} && nmcli connection reload && '
                 f'(nmcli connection up {shlex.quote(args.wifi)} >/dev/null 2>&1 || true)',
                 profile.encode())
            print('Wi-Fi: ' + sudo(client, args.current,
                                   'sleep 8; nmcli -t -f DEVICE,STATE,CONNECTION dev | grep ^wlan0; '
                                   'ip -4 -br addr show wlan0').strip())
        if args.password:
            sudo(client, args.current, 'chpasswd', f'user:{args.password}\n'.encode())
            print('password of "user" changed')
        elif args.current == '1234':
            print('NOTE: "user" still has the default password 1234 - set one with --password')
    finally:
        client.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
