// SPDX-License-Identifier: GPL-2.0-only
/*
 * Ilitek ILI9881H TDDI touchscreen driver (SPI)
 *
 * Used by the Xiaomi Redmi 8 (olive), where the touch controller lives inside
 * the ILI9881H display driver IC and is reached over blsp1_spi3.
 *
 * The wire protocol is taken from the GPL-2.0 vendor driver
 *   drivers/input/touchscreen/ili9881h/  (c) 2011 ILI Technology Corporation,
 *   Author: Dicky Chiang <dicky_chiang@ilitek.com>
 * and reduced to what a mainline touchscreen driver actually needs: bring the
 * IC into "ICE" transfer mode, take the RX lock, read the report packet,
 * release the lock, leave ICE mode again.
 */

#include <linux/bitops.h>
#include <linux/delay.h>
#include <linux/gpio/consumer.h>
#include <linux/input.h>
#include <linux/input/mt.h>
#include <linux/interrupt.h>
#include <linux/kernel.h>
#include <linux/mod_devicetable.h>
#include <linux/module.h>
#include <linux/property.h>
#include <linux/slab.h>
#include <linux/spi/spi.h>
#include <linux/unaligned.h>

/* SPI command bytes */
#define ILI_SPI_WRITE			0x82
#define ILI_SPI_READ			0x83
#define ILI_SPI_ACK			0xa3

/* ICE mode enable/disable magic */
#define ILI_ICE_ENABLE_1		0x1f
#define ILI_ICE_DISABLE_1		0x1b

/* Lock words exchanged with the firmware */
#define ILI_RX_LOCKED			0x5aa5
#define ILI_TX_UNLOCKED			0x9881

/* Report packet IDs */
#define ILI_PKT_DEMO			0x5a

/* Firmware commands */
#define ILI_CMD_MODE_CONTROL		0xf0
#define ILI_FW_DEMO_MODE		0x00

#define ILI_MAX_PACKET			2048
#define ILI_DEMO_PACKET_LEN		43
#define ILI_MAX_FINGERS			10

/* Internal coordinate resolution reported by the firmware */
#define ILI_TPD_RESOLUTION		2048

#define ILI_DEFAULT_SIZE_X		720
#define ILI_DEFAULT_SIZE_Y		1520

struct ili9881h_ts {
	struct spi_device *spi;
	struct input_dev *input;
	struct gpio_desc *reset_gpio;
	u32 size_x;
	u32 size_y;
	u8 *buf;
};

/*
 * All transfers are "send a short command, then optionally clock in a reply"
 * with chip select held across both halves - exactly what spi_write_then_read()
 * does.
 */
static int ili_xfer(struct ili9881h_ts *ts, const void *tx, unsigned int tx_len,
		    void *rx, unsigned int rx_len)
{
	return spi_write_then_read(ts->spi, tx, tx_len, rx, rx_len);
}

static int ili_ice_enable(struct ili9881h_ts *ts)
{
	static const u8 tx[5] = { ILI_SPI_WRITE, ILI_ICE_ENABLE_1, 0x62, 0x10, 0x18 };
	u8 ack = 0;
	int ret;

	/* A lone 0x82 must be answered with 0xa3 before the IC accepts commands */
	ret = ili_xfer(ts, tx, 1, &ack, 1);
	if (ret)
		return ret;

	if (ack != ILI_SPI_ACK) {
		dev_dbg(&ts->spi->dev, "no SPI ACK (0x%02x)\n", ack);
		return -EAGAIN;
	}

	return ili_xfer(ts, tx, sizeof(tx), NULL, 0);
}

static int ili_ice_disable(struct ili9881h_ts *ts)
{
	static const u8 tx[5] = { ILI_SPI_WRITE, ILI_ICE_DISABLE_1, 0x62, 0x10, 0x18 };

	return ili_xfer(ts, tx, sizeof(tx), NULL, 0);
}

/*
 * Ask the firmware whether a packet is waiting. It flips the lock word to
 * 0x5aa5 and puts the packet length in the first two bytes.
 */
#include "ili9881h-ram-loader.h"

static int ili_rx_lock_check(struct ili9881h_ts *ts, unsigned int *size)
{
	u8 tx[5] = { ILI_SPI_WRITE, 0x25, 0x94, 0x00, 0x02 };
	u8 rx[4] = { 0 };
	int ret;

	ret = ili_xfer(ts, tx, sizeof(tx), NULL, 0);
	if (ret)
		return ret;

	tx[0] = ILI_SPI_READ;
	ret = ili_xfer(ts, tx, 1, rx, sizeof(rx));
	if (ret)
		return ret;

	if (get_unaligned_be16(&rx[2]) != ILI_RX_LOCKED)
		return -ENODATA;

	*size = get_unaligned_be16(&rx[0]);
	return 0;
}

/* Read the pending packet and hand the buffer back to the firmware. */
static int ili_unlock_read(struct ili9881h_ts *ts, u8 *data, unsigned int size)
{
	u8 tx[9] = { ILI_SPI_WRITE, 0x25, 0x98, 0x00, 0x02 };
	int ret;

	ret = ili_xfer(ts, tx, 5, NULL, 0);
	if (ret)
		return ret;

	tx[0] = ILI_SPI_READ;
	ret = ili_xfer(ts, tx, 1, data, size);
	if (ret)
		return ret;

	tx[0] = ILI_SPI_WRITE;
	tx[1] = 0x25;
	tx[2] = 0x94;
	tx[3] = 0x00;
	tx[4] = 0x02;
	put_unaligned_be16(size, &tx[5]);
	put_unaligned_be16(ILI_TX_UNLOCKED, &tx[7]);

	return ili_xfer(ts, tx, sizeof(tx), NULL, 0);
}

static int ili_tx_unlock_check(struct ili9881h_ts *ts)
{
	u8 tx[5] = { ILI_SPI_WRITE, 0x25, 0x00, 0x00, 0x02 };
	u8 rx[4] = { 0 };
	int i, ret;

	for (i = 0; i < 100; i++) {
		tx[0] = ILI_SPI_WRITE;
		ret = ili_xfer(ts, tx, sizeof(tx), NULL, 0);
		if (ret)
			return ret;

		tx[0] = ILI_SPI_READ;
		ret = ili_xfer(ts, tx, 1, rx, sizeof(rx));
		if (ret)
			return ret;

		if (get_unaligned_be16(&rx[2]) == ILI_TX_UNLOCKED)
			return 0;

		usleep_range(1000, 1500);
	}

	return -ETIMEDOUT;
}

static u8 ili_checksum(const u8 *data, unsigned int len)
{
	unsigned int i;
	s32 sum = 0;

	for (i = 0; i < len; i++)
		sum += data[i];

	return (u8)((-sum) & 0xff);
}

/* Send a command packet to the firmware (used for mode control). */
static int ili_write_cmd(struct ili9881h_ts *ts, const u8 *cmd, unsigned int len)
{
	unsigned int payload = len + 1;		/* command bytes plus checksum */
	unsigned int padded = round_up(payload, 4);
	u8 *tx;
	int ret;

	tx = kzalloc(padded + 9, GFP_KERNEL);
	if (!tx)
		return -ENOMEM;

	ret = ili_ice_enable(ts);
	if (ret)
		goto out_free;

	tx[0] = ILI_SPI_WRITE;
	tx[1] = 0x25;
	tx[2] = 0x04;
	tx[3] = 0x00;
	tx[4] = 0x02;
	memcpy(&tx[5], cmd, len);
	tx[5 + len] = ili_checksum(cmd, len);

	ret = ili_xfer(ts, tx, padded + 5, NULL, 0);
	if (ret)
		goto out_disable;

	tx[0] = ILI_SPI_WRITE;
	tx[1] = 0x25;
	tx[2] = 0x00;
	tx[3] = 0x00;
	tx[4] = 0x02;
	put_unaligned_be16(payload, &tx[5]);
	put_unaligned_be16(ILI_RX_LOCKED, &tx[7]);

	ret = ili_xfer(ts, tx, 9, NULL, 0);
	if (ret)
		goto out_disable;

	ret = ili_tx_unlock_check(ts);

out_disable:
	ili_ice_disable(ts);
out_free:
	kfree(tx);
	return ret;
}

static void ili_report(struct ili9881h_ts *ts, const u8 *buf, unsigned int len)
{
	struct input_dev *input = ts->input;
	unsigned int i;

	for (i = 0; i < ILI_MAX_FINGERS; i++) {
		const u8 *p = &buf[4 * i + 1];
		unsigned int x, y, pressure;
		bool down;

		if (4 * i + 4 >= len)
			break;

		down = !(p[0] == 0xff && p[1] == 0xff && p[2] == 0xff);

		input_mt_slot(input, i);
		if (!input_mt_report_slot_state(input, MT_TOOL_FINGER, down))
			continue;

		x = ((p[0] & 0xf0) << 4) | p[1];
		y = ((p[0] & 0x0f) << 8) | p[2];
		pressure = p[3];

		/* firmware coordinates are relative to a 2048x2048 grid */
		x = min(x * ts->size_x / ILI_TPD_RESOLUTION, ts->size_x - 1);
		y = min(y * ts->size_y / ILI_TPD_RESOLUTION, ts->size_y - 1);

		input_report_abs(input, ABS_MT_POSITION_X, x);
		input_report_abs(input, ABS_MT_POSITION_Y, y);
		input_report_abs(input, ABS_MT_TOUCH_MAJOR, pressure ?: 1);
		input_report_abs(input, ABS_MT_PRESSURE, pressure ?: 1);
	}

	input_mt_sync_frame(input);
	input_sync(input);
}

static irqreturn_t ili9881h_irq(int irq, void *dev_id)
{
	struct ili9881h_ts *ts = dev_id;
	struct device *dev = &ts->spi->dev;
	unsigned int size = 0;
	int ret;

	ret = ili_ice_enable(ts);
	if (ret) {
		/* The IC is asleep or the panel is off - nothing to do. */
		return IRQ_HANDLED;
	}

	ret = ili_rx_lock_check(ts, &size);
	if (ret || !size || size > ILI_MAX_PACKET) {
		ili_ice_disable(ts);
		if (!ret)
			dev_info_ratelimited(dev, "implausible packet length %u\n", size);
		return IRQ_HANDLED;
	}

	ret = ili_unlock_read(ts, ts->buf, size);
	ili_ice_disable(ts);
	if (ret) {
		dev_dbg(dev, "packet read failed: %d\n", ret);
		return IRQ_HANDLED;
	}

	if (ili_checksum(ts->buf, size - 1) != ts->buf[size - 1]) {
		dev_info_ratelimited(dev, "bad checksum\n");
		return IRQ_HANDLED;
	}

	if (ts->buf[0] == ILI_PKT_DEMO && size >= ILI_DEMO_PACKET_LEN)
		ili_report(ts, ts->buf, size);
	else
		dev_info_ratelimited(dev, "ignoring packet id 0x%02x (%u bytes)\n", ts->buf[0], size);

	return IRQ_HANDLED;
}

static void ili9881h_reset(struct ili9881h_ts *ts)
{
	if (!ts->reset_gpio)
		return;

	gpiod_set_value_cansleep(ts->reset_gpio, 1);
	msleep(10);
	gpiod_set_value_cansleep(ts->reset_gpio, 0);
	msleep(100);
}

static int ili9881h_probe(struct spi_device *spi)
{
	struct device *dev = &spi->dev;
	struct ili9881h_ts *ts;
	struct input_dev *input;
	int ret;

	if (!spi->irq)
		return dev_err_probe(dev, -EINVAL, "no interrupt configured\n");

	ts = devm_kzalloc(dev, sizeof(*ts), GFP_KERNEL);
	if (!ts)
		return -ENOMEM;

	ts->buf = devm_kzalloc(dev, ILI_MAX_PACKET, GFP_KERNEL);
	if (!ts->buf)
		return -ENOMEM;

	ts->spi = spi;
	spi_set_drvdata(spi, ts);

	spi->bits_per_word = 8;
	ret = spi_setup(spi);
	if (ret)
		return dev_err_probe(dev, ret, "spi_setup failed\n");

	ts->reset_gpio = devm_gpiod_get_optional(dev, "reset", GPIOD_OUT_LOW);
	if (IS_ERR(ts->reset_gpio))
		return dev_err_probe(dev, PTR_ERR(ts->reset_gpio),
				     "failed to get reset gpio\n");

	ts->size_x = ILI_DEFAULT_SIZE_X;
	ts->size_y = ILI_DEFAULT_SIZE_Y;
	device_property_read_u32(dev, "touchscreen-size-x", &ts->size_x);
	device_property_read_u32(dev, "touchscreen-size-y", &ts->size_y);

	input = devm_input_allocate_device(dev);
	if (!input)
		return -ENOMEM;

	ts->input = input;
	input->name = "Ilitek ILI9881H TDDI";
	input->phys = "ili9881h/input0";
	input->id.bustype = BUS_SPI;

	input_set_abs_params(input, ABS_MT_POSITION_X, 0, ts->size_x - 1, 0, 0);
	input_set_abs_params(input, ABS_MT_POSITION_Y, 0, ts->size_y - 1, 0, 0);
	input_set_abs_params(input, ABS_MT_TOUCH_MAJOR, 0, 255, 0, 0);
	input_set_abs_params(input, ABS_MT_PRESSURE, 0, 255, 0, 0);

	ret = input_mt_init_slots(input, ILI_MAX_FINGERS,
				  INPUT_MT_DIRECT | INPUT_MT_DROP_UNUSED);
	if (ret)
		return dev_err_probe(dev, ret, "failed to init MT slots\n");

	ili9881h_reset(ts);

	/* Display was initialised by the bootloader; load volatile touch firmware now. */
	ret = ili_load_ram_firmware(ts);
	if (ret)
		return dev_err_probe(dev, ret, "Touch RAM initialization failed\n");
	{
		static const u8 demo_mode[] = { ILI_CMD_MODE_CONTROL, ILI_FW_DEMO_MODE };
		ret = ili_write_cmd(ts, demo_mode, sizeof(demo_mode));
		if (ret)
			return dev_err_probe(dev, ret, "Touch firmware did not acknowledge demo mode\n");
	}

	ret = devm_request_threaded_irq(dev, spi->irq, NULL, ili9881h_irq,
					IRQF_ONESHOT, "ili9881h-tddi", ts);
	if (ret)
		return dev_err_probe(dev, ret, "failed to request irq %d\n", spi->irq);

	ret = input_register_device(input);
	if (ret)
		return dev_err_probe(dev, ret, "failed to register input device\n");

	dev_info(dev, "ILI9881H TDDI touchscreen %ux%u on irq %d\n",
		 ts->size_x, ts->size_y, spi->irq);
	return 0;
}

static const struct of_device_id ili9881h_of_match[] = {
	{ .compatible = "ilitek,ili9881h-tddi" },
	{ }
};
MODULE_DEVICE_TABLE(of, ili9881h_of_match);

static const struct spi_device_id ili9881h_spi_id[] = {
	{ "ili9881h-tddi" },
	{ }
};
MODULE_DEVICE_TABLE(spi, ili9881h_spi_id);

static struct spi_driver ili9881h_driver = {
	.driver = {
		.name = "ili9881h-tddi-fb",
		.of_match_table = ili9881h_of_match,
	},
	.id_table = ili9881h_spi_id,
	.probe = ili9881h_probe,
};
module_spi_driver(ili9881h_driver);

MODULE_DESCRIPTION("Ilitek ILI9881H TDDI SPI touchscreen driver");
MODULE_LICENSE("GPL");
