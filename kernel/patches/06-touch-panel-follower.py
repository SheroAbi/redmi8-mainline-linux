#!/usr/bin/env python3
"""Step 06: tie the volatile TDDI firmware to panel power (DRM panel
follower); a5xx: keep the high half of the UCHE trap address.

    python3 06-touch-panel-follower.py <kernel-tree>
"""
from pathlib import Path
import sys

if len(sys.argv) != 2:
    sys.exit(__doc__)
root = Path(sys.argv[1])
p = root / 'drivers/input/touchscreen/ili9881h-tddi.c'
s = p.read_text()
assert 'olive_panel_prepared' not in s, 'Already patched'
s = s.replace('#include <linux/bitops.h>', '#include <drm/drm_panel.h>\n\n#include <linux/bitops.h>')
s = s.replace('\tu8 *buf;\n};', '\tu8 *buf;\n\tstruct drm_panel_follower follower;\n\tbool ready;\n\tint start_error;\n};')
start = s.index('\tili9881h_reset(ts);', s.index('static int ili9881h_probe'))
end = s.index('\n\tret = devm_request_threaded_irq', start)
s = s[:start] + s[end:]
s = s.replace('IRQF_ONESHOT, "ili9881h-tddi", ts);', 'IRQF_ONESHOT | IRQF_NO_AUTOEN, "ili9881h-tddi", ts);')
mark = '\n\tdev_info(dev, "ILI9881H TDDI touchscreen'
idx = s.index(mark)
s = s[:idx] + '''
	/* Registered after input/IRQ resources so removal quiesces them first. */
	ts->follower.funcs = &olive_panel_follower_funcs;
	ret = devm_drm_panel_add_follower(dev, &ts->follower);
	if (ret)
		return dev_err_probe(dev, ret, "Touch panel dependency unavailable\\n");
	if (ts->start_error)
		return dev_err_probe(dev, ts->start_error,
				     "Touch firmware startup failed\\n");
''' + s[idx:]
idx = s.index('static int ili9881h_probe')
s = s[:idx] + '''/* The display and touch share power inside the TDDI package. */
static int olive_panel_prepared(struct drm_panel_follower *follower)
{
	struct ili9881h_ts *ts = container_of(follower, struct ili9881h_ts, follower);
	static const u8 demo[] = { ILI_CMD_MODE_CONTROL, ILI_FW_DEMO_MODE };
	int ret;

	if (ts->ready)
		return 0;
	ili9881h_reset(ts);
	ret = ili_load_ram_firmware(ts);
	if (!ret)
		ret = ili_write_cmd(ts, demo, sizeof(demo));
	ts->start_error = ret;
	if (ret) {
		dev_err(&ts->spi->dev, "Touch restart after panel prepare failed: %d\\n", ret);
		return ret;
	}
	ts->ready = true;
	enable_irq(ts->spi->irq);
	dev_info(&ts->spi->dev, "Touch ready after panel prepare\\n");
	return 0;
}

static int olive_panel_unpreparing(struct drm_panel_follower *follower)
{
	struct ili9881h_ts *ts = container_of(follower, struct ili9881h_ts, follower);
	int slot;

	if (!ts->ready)
		return 0;
	/* Wait for any in-flight SPI report before the panel removes power. */
	disable_irq(ts->spi->irq);
	ts->ready = false;
	for (slot = 0; slot < ILI_MAX_FINGERS; slot++) {
		input_mt_slot(ts->input, slot);
		input_mt_report_slot_state(ts->input, MT_TOOL_FINGER, false);
	}
	input_mt_sync_frame(ts->input);
	input_sync(ts->input);
	if (ts->reset_gpio)
		gpiod_set_value_cansleep(ts->reset_gpio, 1);
	return 0;
}

static const struct drm_panel_follower_funcs olive_panel_follower_funcs = {
	.panel_prepared = olive_panel_prepared,
	.panel_unpreparing = olive_panel_unpreparing,
};

''' + s[idx:]
p.write_text(s)
p = root / 'arch/arm64/boot/dts/qcom/sdm439-xiaomi-olive.dts'
s = p.read_text().replace('\tpanel@0 {', '\tolive_panel: panel@0 {')
s = s.replace('\t\ttouchscreen-size-x = <720>;', '\t\tpanel = <&olive_panel>;\n\t\ttouchscreen-size-x = <720>;')
p.write_text(s)
p = root / 'drivers/input/touchscreen/Kconfig'
s = p.read_text()
start = s.index('config TOUCHSCREEN_ILI9881H_TDDI')
end = s.index('\nconfig ', start + 1)
block = s[start:end]
block = block.replace('depends on SPI', 'depends on SPI && DRM_PANEL')
s = s[:start] + block + s[end:]
p.write_text(s)
# Retain both halves of the fault address in diagnostics.
p = root / 'drivers/gpu/drm/msm/adreno/a5xx_gpu.c'
s = p.read_text().replace('(uint64_t) gpu_read(gpu, REG_A5XX_UCHE_TRAP_LOG_HI);', '(uint64_t) gpu_read(gpu, REG_A5XX_UCHE_TRAP_LOG_HI) << 32;')
p.write_text(s)
print('Panel follower, DT dependency, and complete GPU fault address patched')
