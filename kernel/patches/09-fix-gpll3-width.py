#!/usr/bin/env python3
"""Step 09: declare the four-bit GPLL3 post-divider (GPU at 450 MHz, not 700).

    python3 09-fix-gpll3-width.py <kernel-tree>
"""
from pathlib import Path
import sys

if len(sys.argv) != 2:
    sys.exit(__doc__)
root = Path(sys.argv[1])
p=root/'drivers/clk/qcom/gcc-msm8917.c'
s=p.read_text()
needle='''static struct clk_alpha_pll_postdiv gpll3 = {
\t.offset = 0x22000,
\t.regs = clk_alpha_pll_regs[CLK_ALPHA_PLL_TYPE_DEFAULT],'''
assert s.count(needle)==1
assert '.width = 4' not in s[s.index(needle):s.index(needle)+220]
s=s.replace(needle, needle+'''
\t/* USER_CTL[11:8]; zero width makes rate negotiation allow only /1. */
\t.width = 4,''')
p.write_text(s)
# During bring-up, diagnostic scripts added sensor probes to the touch
# driver and saved the clean file next to it. On a replay without them there
# is nothing to undo.
touch = root / 'drivers/input/touchscreen/ili9881h-tddi.c'
clean = touch.with_suffix('.before-sensor-probe.c')
if clean.exists():
    assert 'sensor_probe' not in clean.read_text()
    touch.write_text(clean.read_text())
    clean.unlink()
assert 'sensor_probe' not in touch.read_text()
print('GPLL3 divider width fixed')
