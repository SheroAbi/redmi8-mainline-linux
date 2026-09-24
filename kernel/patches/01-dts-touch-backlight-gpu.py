#!/usr/bin/env python3
"""Step 01: olive device tree and panel driver -- touch SPI bus, LM3697
backlight wiring, GPU node enabled.

    python3 01-dts-touch-backlight-gpu.py <kernel-tree>

Expects the tree after 00-olive-display-touch-v2.patch and pmaports'
0001-0003. Every edit asserts on the text it replaces, so running it twice or
on the wrong tree stops with an error instead of half-applying.
"""
import sys
import pathlib

if len(sys.argv) != 2:
    sys.exit(__doc__)
SRC = pathlib.Path(sys.argv[1])
DTS = SRC / "arch/arm64/boot/dts/qcom/sdm439-xiaomi-olive.dts"
PANEL = SRC / "drivers/gpu/drm/panel/msm89x7-generated/panel-ili9881hplus-c3i.c"


def must(cond, msg):
    if not cond:
        sys.exit("ERROR: " + msg)


# ---------------------------------------------------------------- DTS
s = DTS.read_text()

# 1) enable the touch SPI bus, add the ILI9881H TDDI node
old_spi = '''&blsp1_spi3 {
\tstatus = "disabled";

\t/* ilitek,ili9881h@0 */
\t/* novatek,nt36525b@1 */
\t/* focaltech,ft8006s@2 */
};'''
new_spi = '''&blsp1_spi3 {
\tstatus = "okay";

\ttouchscreen@0 {
\t\tcompatible = "ilitek,ili9881h-tddi";
\t\treg = <0>;

\t\tspi-max-frequency = <10000000>;
\t\tspi-cpol;
\t\tspi-cpha;

\t\tinterrupts-extended = <&tlmm 65 IRQ_TYPE_EDGE_FALLING>;
\t\treset-gpios = <&tlmm 64 GPIO_ACTIVE_LOW>;

\t\ttouchscreen-size-x = <720>;
\t\ttouchscreen-size-y = <1520>;

\t\tpinctrl-0 = <&ts_default>;
\t\tpinctrl-names = "default";
\t};

\t/* novatek,nt36525b@1 */
\t/* focaltech,ft8006s@2 */
};'''
must(old_spi in s, "blsp1_spi3 block not found")
s = s.replace(old_spi, new_spi, 1)

# 2) enable the I2C bus and the LM3697
old_i2c_head = '&blsp2_i2c1 {\n\tstatus = "disabled";'
must(old_i2c_head in s, "blsp2_i2c1 header not found")
s = s.replace(old_i2c_head, '&blsp2_i2c1 {\n\tstatus = "okay";', 1)

old_lm = '''\t\tenable-gpios = <&pm8953_gpios 4 GPIO_ACTIVE_HIGH>;
\t\tstatus = "disabled";'''
must(old_lm in s, "lm3697 status not found")
s = s.replace(old_lm, '''\t\tenable-gpios = <&pm8953_gpios 4 GPIO_ACTIVE_HIGH>;
\t\tstatus = "okay";''', 1)

# 3) LED node: 11-bit resolution like stock, no legacy trigger
old_led = '''\t\t\tti,brightness-resolution = <255>;
\t\t\tramp-up-us = <200000>;
\t\t\tramp-down-us = <200000>;
\t\t\tlabel = "white:backlight";
\t\t\tlinux,default-trigger = "backlight";'''
new_led = '''\t\t\tti,brightness-resolution = <2047>;
\t\t\tramp-up-us = <200000>;
\t\t\tramp-down-us = <200000>;
\t\t\tlabel = "white:backlight";'''
must(old_led in s, "lm3697 led node not found")
s = s.replace(old_led, new_led, 1)

# 4) led-backlight node in the root block (before gpio-keys)
anchor = '''\tgpio-keys {
\t\tcompatible = "gpio-keys";'''
must(anchor in s, "gpio-keys anchor not found")
s = s.replace(anchor, '''\tbacklight_lcd: backlight {
\t\tcompatible = "led-backlight";
\t\tleds = <&lm3697_leds>;
\t\tdefault-brightness-level = <1024>;
\t};

''' + anchor, 1)

# 5) the panel gets the external backlight
old_panel = '''\t\treset-gpios = <&tlmm 60 GPIO_ACTIVE_LOW>;
\t\tvdd-supply = <&pm8953_l17>;
\t\tvddio-supply = <&pm8953_l6>;'''
must(old_panel in s, "panel node not found")
s = s.replace(old_panel, '''\t\tbacklight = <&backlight_lcd>;
\t\treset-gpios = <&tlmm 60 GPIO_ACTIVE_LOW>;
\t\tvdd-supply = <&pm8953_l17>;
\t\tvddio-supply = <&pm8953_l6>;''', 1)

# 6) touch pinctrl in the tlmm block
old_tlmm = '\tsdc2_cd_default: sdc2-cd-default-state {'
must(old_tlmm in s, "tlmm sdc2 anchor not found")
s = s.replace(old_tlmm, '''\tts_default: ts-default-state {
\t\tts-irq-pins {
\t\t\tpins = "gpio65";
\t\t\tfunction = "gpio";
\t\t\tdrive-strength = <8>;
\t\t\tbias-pull-up;
\t\t};

\t\tts-reset-pins {
\t\t\tpins = "gpio64";
\t\t\tfunction = "gpio";
\t\t\tdrive-strength = <8>;
\t\t\tbias-pull-up;
\t\t};
\t};

''' + old_tlmm, 1)

# 7) enable the GPU (Adreno 505); msm is a module, so this is boot-safe
must(s.rstrip().endswith('};'), "unexpected end of the DTS")
s = s.rstrip() + '''

&gpu {
\tstatus = "okay";
};
'''
DTS.write_text(s)
print("DTS ok")

# ---------------------------------------------------------------- Panel
BS = chr(92)  # a literal backslash, so no escaping accident can happen
p = PANEL.read_text()

start = '\tctx->panel.backlight = ili9881hplus_c3i_create_backlight(dsi);'
must(start in p, "panel: create_backlight line not found")
i = p.index(start)
tail = p[i:]
endmark = '"Failed to create backlight' + BS + 'n");'
must(endmark in tail, "panel: end of the error message not found")
j = i + tail.index(endmark) + len(endmark)
old_block = p[i:j]
must(old_block.count('\n') == 3, "panel: unexpected block size: " + repr(old_block))

new_block = (
    '\t/*\n'
    '\t * Olive drives its backlight through an external LM3697 LED driver,\n'
    '\t * described via a "backlight" phandle.  Only fall back to the panel\'s\n'
    '\t * own DCS backlight when no external one is described.\n'
    '\t */\n'
    '\tret = drm_panel_of_backlight(&ctx->panel);\n'
    '\tif (ret)\n'
    '\t\treturn dev_err_probe(dev, ret, "Failed to get backlight' + BS + 'n");\n'
    '\n'
    '\tif (!ctx->panel.backlight) {\n'
    '\t\tctx->panel.backlight = ili9881hplus_c3i_create_backlight(dsi);\n'
    '\t\tif (IS_ERR(ctx->panel.backlight))\n'
    '\t\t\treturn dev_err_probe(dev, PTR_ERR(ctx->panel.backlight),\n'
    '\t\t\t\t\t     "Failed to create backlight' + BS + 'n");\n'
    '\t}'
)
p = p[:i] + new_block + p[j:]
PANEL.write_text(p)
print("Panel ok")
