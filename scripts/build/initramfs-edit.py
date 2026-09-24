#!/usr/bin/env python3
"""Edit one file inside a gzip'd newc initramfs, byte-exact everywhere else.

    python initramfs-edit.py IN OUT --check
        rebuild without changes and prove the result is identical
    python initramfs-edit.py IN OUT --extract NAME DEST
    python initramfs-edit.py IN OUT --replace NAME NEWFILE

Every other entry (device nodes, symlinks, hard links, modules) is copied as
the raw bytes it was, so only the replaced file can differ. Runs on Windows,
where the device has no cpio and WSL may be off.
"""
import gzip
import sys


def entries(data):
    i = 0
    while i < len(data):
        if data[i:i+6] not in (b'070701', b'070702'):
            # Trailing padding after TRAILER!!!.
            yield None, data[i:], None
            return
        head = data[i:i+110]
        fields = [int(head[6+8*k:14+8*k], 16) for k in range(13)]
        filesize, namesize = fields[6], fields[11]
        name = data[i+110:i+110+namesize-1].decode()
        data_start = (i+110+namesize+3) & ~3
        end = (data_start+filesize+3) & ~3
        yield name, data[i:end], (head, data[i+110:data_start], data[data_start:data_start+filesize])
        i = end


def rebuild(raw, replace=None):
    out = []
    for name, chunk, parts in entries(raw):
        if name is not None and replace and name == replace[0]:
            head, name_part, _old = parts
            new = replace[1]
            head = head[:54] + b'%08X' % len(new) + head[62:]
            # Data starts 4-aligned (name_part carries that padding), so the
            # padding after it only depends on the data length.
            out.append(head + name_part + new + b'\0' * (-len(new) % 4))
            continue
        out.append(chunk)
    return b''.join(out)


def main():
    src, dst, mode = sys.argv[1], sys.argv[2], sys.argv[3]
    raw = gzip.open(src, 'rb').read()
    if mode == '--check':
        again = rebuild(raw)
        print('identical' if again == raw else 'DIFFERENT', len(raw))
        return 0 if again == raw else 1
    if mode == '--extract':
        for name, _chunk, parts in entries(raw):
            if name == sys.argv[4]:
                open(sys.argv[5], 'wb').write(parts[2])
                return 0
        raise SystemExit('not found: ' + sys.argv[4])
    if mode == '--replace':
        new = open(sys.argv[5], 'rb').read().replace(b'\r\n', b'\n')
        names = [name for name, _c, _p in entries(raw)]
        if sys.argv[4] not in names:
            raise SystemExit('not found: ' + sys.argv[4])
        result = rebuild(raw, (sys.argv[4], new))
        with gzip.GzipFile(dst, 'wb', compresslevel=9, mtime=0) as f:
            f.write(result)
        # Prove the new archive parses and carries exactly the new file.
        check = gzip.open(dst, 'rb').read()
        got = {name: parts[2] for name, _c, parts in entries(check) if name}
        assert got[sys.argv[4]] == new, 'replacement did not land'
        assert sorted(got) == sorted(n for n in names if n), 'entry list changed'
        print('written', dst, len(check))
        return 0
    raise SystemExit('unknown mode ' + mode)


if __name__ == '__main__':
    raise SystemExit(main())
