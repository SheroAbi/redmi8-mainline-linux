#!/usr/bin/env python3
"""Convert the vendor kernel's ILI9881H touch firmware array to the raw file
the touch driver loads.

    python3 firmware/convert-touch-firmware.py C3I_TIANMA_6217_LongH_V0x04.ili [OUT]

The input is the text array of hex bytes from the vendor kernel source
(drivers/input/touchscreen/ili9881h/.../ITK9881H/). The bytes are not changed:
the script parses them, checks the three blocks (AP, DATA, TUNING) against the
CRC32 each carries, and writes them out as binary. Default OUT is
firmware/ilitek/olive-ili9881h-c3i-0x04.ili.
"""
from pathlib import Path
import hashlib
import re
import sys

if len(sys.argv) not in (2, 3):
    sys.exit(__doc__)
source = Path(sys.argv[1])
out = Path(sys.argv[2]) if len(sys.argv) == 3 else \
    Path(__file__).resolve().parent / 'ilitek/olive-ili9881h-c3i-0x04.ili'
data = bytes(int(x, 16) for x in re.findall(r'0x([0-9a-fA-F]{2})\b', source.read_text()))
assert len(data) >= 64 + 0x12200, 'too short for an ILI9881H firmware'
assert data[32] & 7 == 7, 'unexpected block flags'


def crc(block):
    result = 0xffffffff
    for value in block:
        result ^= value << 24
        for _ in range(8):
            result = ((result << 1) ^ (0x04c11db7 if result & 0x80000000 else 0)) & 0xffffffff
    return result


for index, name in enumerate(('AP', 'DATA', 'TUNING')):
    start = int.from_bytes(data[34 + index * 6:37 + index * 6], 'big')
    end = int.from_bytes(data[37 + index * 6:40 + index * 6], 'big')
    block = data[64 + start:64 + end + 1]
    assert len(block) == end - start + 1 and len(block) > 4, name
    assert crc(block[:-4]) == int.from_bytes(block[-4:], 'big'), f'{name}: CRC mismatch'
    print(f'{name:6} {start:#07x}-{end:#07x} crc ok')
out.write_bytes(data)
print(f'{out}: {len(data)} bytes, sha256 {hashlib.sha256(data).hexdigest()}')
