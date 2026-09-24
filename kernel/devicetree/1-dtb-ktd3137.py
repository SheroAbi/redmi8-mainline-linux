#!/usr/bin/env python3
"""olive DTB: replace LM3697 + led-backlight with the KTD3137 actually fitted.

The panel keeps its backlight phandle: the new node takes over the phandle
of the old led-backlight node.  usage: r8-dtb-ktd.py in.dtb out.dtb
"""
import sys
import fdt

t = fdt.parse_dtb(open(sys.argv[1], 'rb').read())
soc = [n for n in t.root.nodes if n.name.startswith('soc')][0]
i2c = [n for n in soc.nodes if n.name == 'i2c@7af5000'][0]
lm = [n for n in i2c.nodes if n.name.startswith('lm3697')][0]
gpios = lm.get_property('enable-gpios').data
bl = t.root.get_subnode('backlight')
assert bl.get_property('compatible').value == 'led-backlight'
ph = bl.get_property('phandle').value

t.root.remove_subnode('backlight')
i2c.remove_subnode(lm.name)
k = fdt.Node('backlight@36')
k.append(fdt.PropStrings('compatible', 'kinetic,ktd3137'))
k.append(fdt.PropWords('reg', 0x36))
k.append(fdt.PropWords('enable-gpios', *gpios))
k.append(fdt.PropWords('phandle', ph))
i2c.append(k)

# every remaining reference to the panel backlight must hit the new node
refs = []
def walk(n):
    for p in n.props:
        if p.name == 'backlight':
            refs.append((n.name, p.value))
    for c in n.nodes:
        walk(c)
walk(t.root)
assert refs and all(v == ph for _, v in refs), refs
open(sys.argv[2], 'wb').write(t.to_dtb(version=17))
print('ktd3137 node, phandle', hex(ph), 'enable-gpios', gpios, 'panel refs', refs)
