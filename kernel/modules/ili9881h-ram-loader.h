/* SPDX-License-Identifier: GPL-2.0-only */
/* ILI9881H RAM download, derived from Xiaomi ITK9881H ilitek_fw.c/ic.c.
 * Only volatile application/data/tuning RAM is written; no flash commands.
 */
#include <linux/crc32.h>
#include <linux/firmware.h>

#define OLIVE_ILI_FW "ilitek/olive-ili9881h-c3i-0x04.ili"
#define ILI_RAM_CHUNK 1024

struct ili_ram_block {
	u32 start, len, target;
};

static u32 ili_be24(const u8 *p)
{
	return (p[0] << 16) | (p[1] << 8) | p[2];
}

static int ili_ram_read(struct ili9881h_ts *ts, u32 addr, void *buf, size_t size)
{
	u8 cmd[] = { ILI_SPI_WRITE, 0x25, addr, addr >> 8, addr >> 16 };
	u8 read = ILI_SPI_READ;
	int ret = ili_xfer(ts, cmd, sizeof(cmd), NULL, 0);

	return ret ?: ili_xfer(ts, &read, 1, buf, size);
}

static int ili_ram_write_byte(struct ili9881h_ts *ts, u32 addr, u8 value)
{
	u8 cmd[] = { ILI_SPI_WRITE, 0x25, addr, addr >> 8, addr >> 16, value };

	return ili_xfer(ts, cmd, sizeof(cmd), NULL, 0);
}

static int ili_load_ram_firmware(struct ili9881h_ts *ts)
{
	struct device *dev = &ts->spi->dev;
	const struct firmware *fw;
	struct ili_ram_block blocks[3];
	const u8 enter[] = { ILI_SPI_WRITE, 0x25, 0x62, 0x10, 0x18 };
	u8 pid[4], state = 0, *tx = NULL, *verify = NULL;
	u32 index, offset, address, size, end, target, chip_id;
	bool ice_entered = false;
	int ret, tries;

	ret = request_firmware(&fw, OLIVE_ILI_FW, dev);
	if (ret)
		return dev_err_probe(dev, ret, "Touch RAM firmware unavailable\n");
	ret = -EINVAL;
	if (fw->size != 127040 || (fw->data[32] & 7) != 7)
		goto out;
	for (index = 0; index < ARRAY_SIZE(blocks); index++) {
		blocks[index].start = ili_be24(fw->data + 34 + index * 6);
		end = ili_be24(fw->data + 37 + index * 6);
		if (end < blocks[index].start || end >= fw->size - 64)
			goto out;
		blocks[index].len = end - blocks[index].start + 1;
		if (blocks[index].len < 5)
			goto out;
		blocks[index].target = index == 0 ? 0 :
			(index == 1 ? 0x20610 : blocks[1].target + blocks[1].len);
		if (fw->data[32] & 0x80) {
			for (offset = 0; offset < 3; offset++) {
				target = ili_be24(fw->data + 6 + offset * 4);
				if (target && fw->data[9 + offset * 4] == index + 1)
					blocks[index].target = target;
			}
		}
		address = blocks[index].target;
		if (index == 0 ? (address != 0 || blocks[index].len > 0x10000) :
		    (address < 0x20000 || address >= 0x24000 ||
		     blocks[index].len > 0x24000 - address))
			goto out;
		if (crc32_be(~0U, fw->data + 64 + blocks[index].start,
			     blocks[index].len - 4) !=
		    get_unaligned_be32(fw->data + 64 + end - 3)) {
			dev_err(dev, "Firmware block %u CRC mismatch\n", index);
			goto out;
		}
	}
	tx = kmalloc(ILI_RAM_CHUNK + 5, GFP_KERNEL);
	verify = kmalloc(ILI_RAM_CHUNK, GFP_KERNEL);
	if (!tx || !verify) {
		ret = -ENOMEM;
		goto out;
	}

	/* Halt only the touch MCU; confirm its identity before any register write. */
	ret = ili_xfer(ts, enter, sizeof(enter), NULL, 0);
	if (ret)
		goto out;
	ice_entered = true;
	ret = ili_ram_read(ts, 0x4009c, pid, sizeof(pid));
	if (ret)
		goto out;
	chip_id = get_unaligned_le32(pid);
	if ((chip_id >> 16) != 0x9881) {
		dev_err(dev, "Unexpected touch chip ID %08x\n", chip_id);
		ret = -ENODEV;
		goto out;
	}
	dev_info(dev, "Touch chip %08x, loading verified RAM firmware\n", chip_id);
	ret = ili_ram_write_byte(ts, 0x47002, 0);
	if (ret)
		goto out;
	usleep_range(300, 500);
	ret = ili_ram_write_byte(ts, 0x5100c, 0x81);
	if (!ret)
		ret = ili_ram_write_byte(ts, 0x5100c, 0x98);
	if (ret)
		goto out;
	for (tries = 0; tries < 50; tries++) {
		usleep_range(1000, 1500);
		ret = ili_ram_read(ts, 0x51018, &state, 1);
		if (ret || state == 0x5a)
			break;
		ret = ili_ram_write_byte(ts, 0x5100c, 0);
		if (!ret)
			ret = ili_ram_write_byte(ts, 0x5100c, 0x98);
		if (ret)
			break;
	}
	if (!ret && state != 0x5a)
		ret = -ETIMEDOUT;
	if (ret)
		goto out;
	ret = ili_ram_write_byte(ts, 0x5100c, 0);
	if (ret)
		goto out;

	for (index = 0; index < ARRAY_SIZE(blocks); index++) {
		for (offset = 0; offset < blocks[index].len; offset += size) {
			size = min_t(u32, ILI_RAM_CHUNK, blocks[index].len - offset);
			address = blocks[index].target + offset;
			tx[0] = ILI_SPI_WRITE;
			tx[1] = 0x25;
			tx[2] = address;
			tx[3] = address >> 8;
			tx[4] = address >> 16;
			memcpy(tx + 5, fw->data + 64 + blocks[index].start + offset, size);
			ret = ili_xfer(ts, tx, size + 5, NULL, 0);
			if (!ret)
				ret = ili_ram_read(ts, address, verify, size);
			if (ret)
				goto out;
			if (memcmp(tx + 5, verify, size)) {
				dev_err(dev, "Touch RAM readback mismatch at %06x\n", address);
				ret = -EIO;
				goto out;
			}
		}
	}
	ret = ili_ram_write_byte(ts, 0x40040, 0xae);
out:
	if (ice_entered) {
		int exit_ret = ili_ice_disable(ts);
		if (!ret)
			ret = exit_ret;
	}
	kfree(verify);
	kfree(tx);
	release_firmware(fw);
	if (!ret) {
		msleep(100);
		dev_info(dev, "Touch AP/DATA/TUNING RAM readback verified\n");
	}
	return ret;
}
