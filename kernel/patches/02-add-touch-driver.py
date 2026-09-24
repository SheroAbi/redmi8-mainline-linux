#!/usr/bin/env python3
"""Step 02: add the in-tree ILI9881H TDDI touch driver.

    python3 02-add-touch-driver.py <kernel-tree>

Copies src/ili9881h-tddi.c into drivers/input/touchscreen/ and registers it
in Kconfig and the Makefile (CONFIG_TOUCHSCREEN_ILI9881H_TDDI, set to =m in
the shipped config). Steps 05-07 and 09 extend this driver.
"""
import pathlib
import shutil
import sys

if len(sys.argv) != 2:
    sys.exit(__doc__)
tree = pathlib.Path(sys.argv[1])
base = tree / "drivers/input/touchscreen"
here = pathlib.Path(__file__).resolve().parent

driver = base / "ili9881h-tddi.c"
if driver.exists():
    sys.exit(f"ERROR: {driver} already exists - step 02 was applied before")
shutil.copyfile(here / "src/ili9881h-tddi.c", driver)

kc = base / "Kconfig"
s = kc.read_text()
anchor = "config TOUCHSCREEN_ILITEK\n"
if anchor not in s:
    sys.exit("ERROR: TOUCHSCREEN_ILITEK anchor missing in Kconfig")
entry = """config TOUCHSCREEN_ILI9881H_TDDI
\ttristate "Ilitek ILI9881H TDDI touchscreen (SPI)"
\tdepends on SPI
\thelp
\t  Say Y here to enable support for the touch controller embedded in
\t  the Ilitek ILI9881H TDDI display driver IC, as found in the
\t  Xiaomi Redmi 8 (olive).

\t  If unsure, say N.

\t  To compile this driver as a module, choose M here: the module will
\t  be called ili9881h-tddi.

"""
kc.write_text(s.replace(anchor, entry + anchor, 1))

mk = base / "Makefile"
m = mk.read_text()
mark = "obj-$(CONFIG_TOUCHSCREEN_ILITEK)"
if mark not in m:
    sys.exit("ERROR: TOUCHSCREEN_ILITEK line missing in the Makefile")
line = "obj-$(CONFIG_TOUCHSCREEN_ILI9881H_TDDI)\t+= ili9881h-tddi.o\n"
mk.write_text(m.replace(mark, line + mark, 1))
print("ili9881h-tddi added to drivers/input/touchscreen")
