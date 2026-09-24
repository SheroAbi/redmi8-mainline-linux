#!/usr/bin/env python3
"""Add the olive-power node (PMI632 charger 0x1000 + QG 0x4800) and the
battery thermistor ADC channel to an olive DTB.   usage: in.dtb out.dtb"""
import sys
import fdt

t = fdt.parse_dtb(open(sys.argv[1], 'rb').read())


def all_phandles(node, acc):
    p = node.get_property('phandle')
    if p is not None:
        acc.add(p.value)
    for n in node.nodes:
        all_phandles(n, acc)
    return acc


def find(node, name):
    if node.name == name:
        return node
    for n in node.nodes:
        r = find(n, name)
        if r:
            return r
    return None


pmic = find(t.root, 'pmic@2')
adc = [n for n in pmic.nodes if n.name == 'adc@3100'][0]
if adc.get_property('phandle') is None:
    adc.append(fdt.PropWords('phandle', max(all_phandles(t.root, set())) + 1))
adc_ph = adc.get_property('phandle').value

if not adc.exist_subnode('channel@4a'):
    ch = fdt.Node('channel@4a')
    ch.append(fdt.PropWords('reg', 0x4a))
    ch.append(fdt.PropWords('qcom,hw-settle-time', 200))
    ch.append(fdt.PropWords('qcom,pre-scaling', 1, 1))
    ch.append(fdt.Property('qcom,ratiometric'))
    ch.append(fdt.PropStrings('label', 'bat_therm'))
    adc.append(ch)

if not pmic.exist_subnode('charger@1000'):
    c = fdt.Node('charger@1000')
    c.append(fdt.PropStrings('compatible', 'xiaomi,olive-power'))
    c.append(fdt.PropWords('reg', 0x1000))
    c.append(fdt.PropWords('qcom,qg-base', 0x4800))
    c.append(fdt.PropWords('io-channels', adc_ph, 0x08, adc_ph, 0x07, adc_ph, 0x84, adc_ph, 0x4a))
    c.append(fdt.PropStrings('io-channel-names', 'usbin_v', 'usbin_i', 'vbat', 'batt_therm'))
    pmic.append(c)

open(sys.argv[2], 'wb').write(t.to_dtb(version=17))
print('olive-power node added, adc phandle', hex(adc_ph))
