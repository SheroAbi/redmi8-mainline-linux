#!/usr/bin/env python3
"""Step 07: verify replies from the running touch firmware before enabling
reports.

    python3 07-touch-firmware-query.py <kernel-tree>
"""
from pathlib import Path
import sys

if len(sys.argv) != 2:
    sys.exit(__doc__)
p = Path(sys.argv[1]) / 'drivers/input/touchscreen/ili9881h-tddi.c'
s = p.read_text()
assert 'ili_query_firmware' not in s
at = s.index('static void ili_report(')
s = s[:at] + '''/* Called before IRQ enable; consume the complete response to release RX. */
static int ili_query_firmware(struct ili9881h_ts *ts, u8 command)
{
	u8 select[] = { 0xf6, command };
	u8 response[32];
	unsigned int size = 0;
	int ret, tries;

	ret = ili_write_cmd(ts, select, sizeof(select));
	if (!ret)
		ret = ili_write_cmd(ts, &command, 1);
	if (ret)
		return ret;
	for (tries = 0; tries < 20; tries++) {
		usleep_range(1000, 1500);
		ret = ili_ice_enable(ts);
		if (ret)
			return ret;
		ret = ili_rx_lock_check(ts, &size);
		if (!ret && (!size || size > sizeof(response)))
			ret = -EMSGSIZE;
		if (!ret)
			ret = ili_unlock_read(ts, response, size);
		ili_ice_disable(ts);
		if (ret != -ENODATA)
			break;
	}
	if (ret)
		return ret;
	dev_info(&ts->spi->dev, "Firmware query %02x: %*ph\\n",
		 command, size, response);
	return size >= 4 && response[0] == command ? 0 : -EPROTO;
}

''' + s[at:]
needle = '\t\tret = ili_write_cmd(ts, demo, sizeof(demo));\n\tts->start_error = ret;'
assert s.count(needle) == 1
s=s.replace(needle, '''		ret = ili_write_cmd(ts, demo, sizeof(demo));
	if (!ret)
		ret = ili_query_firmware(ts, 0x22);
	if (!ret)
		ret = ili_query_firmware(ts, 0x21);
	ts->start_error = ret;''')
p.write_text(s)
print('Added protocol and firmware response validation before touch IRQ enable')
