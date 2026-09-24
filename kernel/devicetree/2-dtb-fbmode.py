#!/usr/bin/env python3
"""olive DTB for the usable 'fb mode': bootloader display + touch + GPU only.

The DSI/DPU path still leaves the panel uninitialised (no image, and without
panel init no LEDPWM, so the KTD3137 stays dark). Until that is fixed:
  * display-subsystem disabled -> simple-framebuffer keeps the bootloader
    picture and msm can only bind the Adreno as a separate GPU device
  * touchscreen loses its 'panel' link (it would wait for the panel forever)
usage: r8-dtb-fbmode.py in.dtb out.dtb
"""
import sys
import fdt

t = fdt.parse_dtb(open(sys.argv[1], 'rb').read())
soc = [n for n in t.root.nodes if n.name.startswith('soc')][0]
mdss = [n for n in soc.nodes if n.name == 'display-subsystem@1a00000'][0]
mdss.set_property('status', 'disabled')

spi = [n for n in soc.nodes if n.name == 'spi@78b7000'][0]
ts = [n for n in spi.nodes if n.name.startswith('touchscreen')][0]
if ts.exist_property('panel'):
    ts.remove_property('panel')

open(sys.argv[2], 'wb').write(t.to_dtb(version=17))
print('fb-mode DTB:', mdss.get_property('status').value, 'touch panel link removed ->', sys.argv[2])
