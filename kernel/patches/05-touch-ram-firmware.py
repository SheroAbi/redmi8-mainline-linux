#!/usr/bin/env python3
"""Step 05: touch driver loads its RAM firmware at probe; coordinate clamp.

    python3 05-touch-ram-firmware.py <kernel-tree>

Needs ../modules/ili9881h-ram-loader.h (copied next to the driver).
"""
from pathlib import Path
import shutil
import sys

if len(sys.argv) != 2:
    sys.exit(__doc__)
tree = Path(sys.argv[1])
loader = Path(__file__).resolve().parents[1] / 'modules/ili9881h-ram-loader.h'
p = tree / 'drivers/input/touchscreen/ili9881h-tddi.c'
s = p.read_text()
needle = 'static int ili_rx_lock_check('
assert s.count(needle) == 1
s = s.replace(needle, '#include "ili9881h-ram-loader.h"\n\n' + needle, 1)
a = s.index('\t/*\n\t * Do not fail the probe when the IC stays quiet:')
b = s.index('\n\tret = devm_request_threaded_irq', a)
s = s[:a] + '''\t/* The controller loses its executable code at every touch reset. */
\tret = ili_load_ram_firmware(ts);
\tif (ret)
\t\treturn dev_err_probe(dev, ret, "Touch RAM initialization failed\\n");
\t{
\t\tstatic const u8 demo_mode[] = { ILI_CMD_MODE_CONTROL, ILI_FW_DEMO_MODE };
\t\tret = ili_write_cmd(ts, demo_mode, sizeof(demo_mode));
\t\tif (ret)
\t\t\treturn dev_err_probe(dev, ret, "Touch firmware did not acknowledge demo mode\\n");
\t}
''' + s[b:]
s = s.replace('x = x * ts->size_x / ILI_TPD_RESOLUTION;',
              'x = min(x * ts->size_x / ILI_TPD_RESOLUTION, ts->size_x - 1);')
s = s.replace('y = y * ts->size_y / ILI_TPD_RESOLUTION;',
              'y = min(y * ts->size_y / ILI_TPD_RESOLUTION, ts->size_y - 1);')
p.write_text(s)
shutil.copy2(loader, p.with_name('ili9881h-ram-loader.h'))
print('RAM-only firmware initialization and strict probe checks added')
