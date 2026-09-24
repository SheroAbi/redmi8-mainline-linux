// SPDX-License-Identifier: GPL-2.0-only
/*
 * Kinetic KTD3137 LED backlight driver.
 *
 * Used as the second-source backlight IC on the Xiaomi Redmi 8 (olive),
 * at I2C address 0x36 (same address as the LM3697 it replaces).
 *
 * Register layout from the vendor driver, confirmed on hardware: the
 * bootloader leaves MODE=0x99, CONTROL=0x6e, PWM=0x1b and an 11-bit
 * brightness of 2047 (LSB[2:0]=0x07, MSB=0xff).
 */

#include <linux/backlight.h>
#include <linux/delay.h>
#include <linux/gpio/consumer.h>
#include <linux/i2c.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/regmap.h>

#define KTD3137_REG_DEV_ID	0x00
#define KTD3137_REG_MODE	0x02
#define KTD3137_REG_CONTROL	0x03
#define KTD3137_REG_RATIO_LSB	0x04
#define KTD3137_REG_RATIO_MSB	0x05
#define KTD3137_REG_PWM		0x06
#define KTD3137_REG_STATUS	0x0a
#define KTD3137_REG_MAX		0x0a

#define KTD3137_DEV_ID		0x18
#define KTD3137_MAX_BRIGHTNESS	2047

struct ktd3137 {
	struct regmap *regmap;
	struct gpio_desc *enable;
	u32 mode;
	u32 control;
	u32 pwm;
};

static int ktd3137_write_brightness(struct ktd3137 *ktd, unsigned int level)
{
	int ret;

	/* 11-bit ratio: bits [2:0] in LSB, bits [10:3] in MSB (latches) */
	ret = regmap_write(ktd->regmap, KTD3137_REG_RATIO_LSB, level & 0x07);
	if (ret)
		return ret;

	return regmap_write(ktd->regmap, KTD3137_REG_RATIO_MSB, (level >> 3) & 0xff);
}

static int ktd3137_update_status(struct backlight_device *bl)
{
	struct ktd3137 *ktd = bl_get_data(bl);

	return ktd3137_write_brightness(ktd, backlight_get_brightness(bl));
}

static const struct backlight_ops ktd3137_bl_ops = {
	.options = BL_CORE_SUSPENDRESUME,
	.update_status = ktd3137_update_status,
};

static const struct regmap_config ktd3137_regmap_config = {
	.reg_bits = 8,
	.val_bits = 8,
	.max_register = KTD3137_REG_MAX,
};

static int ktd3137_probe(struct i2c_client *client)
{
	struct device *dev = &client->dev;
	struct backlight_properties props = {
		.type = BACKLIGHT_RAW,
		.scale = BACKLIGHT_SCALE_LINEAR,
		.max_brightness = KTD3137_MAX_BRIGHTNESS,
		.brightness = 1024,
	};
	struct backlight_device *bl;
	struct ktd3137 *ktd;
	unsigned int id, lsb, msb;
	int ret;

	ktd = devm_kzalloc(dev, sizeof(*ktd), GFP_KERNEL);
	if (!ktd)
		return -ENOMEM;

	/* Keep the chip enabled: the bootloader already lit the panel. */
	ktd->enable = devm_gpiod_get_optional(dev, "enable", GPIOD_OUT_HIGH);
	if (IS_ERR(ktd->enable))
		return dev_err_probe(dev, PTR_ERR(ktd->enable), "enable gpio\n");

	ktd->regmap = devm_regmap_init_i2c(client, &ktd3137_regmap_config);
	if (IS_ERR(ktd->regmap))
		return PTR_ERR(ktd->regmap);

	ret = regmap_read(ktd->regmap, KTD3137_REG_DEV_ID, &id);
	if (ret)
		return dev_err_probe(dev, ret, "cannot read device id\n");
	if (id != KTD3137_DEV_ID)
		return dev_err_probe(dev, -ENODEV, "unexpected id 0x%02x\n", id);

	/* Defaults are the values the stock bootloader programs. */
	ktd->mode = 0x99;
	ktd->control = 0x6e;
	ktd->pwm = 0x1b;
	of_property_read_u32(dev->of_node, "kinetic,mode", &ktd->mode);
	of_property_read_u32(dev->of_node, "kinetic,control", &ktd->control);
	of_property_read_u32(dev->of_node, "kinetic,pwm", &ktd->pwm);

	ret = regmap_write(ktd->regmap, KTD3137_REG_CONTROL, ktd->control);
	if (!ret)
		ret = regmap_write(ktd->regmap, KTD3137_REG_PWM, ktd->pwm);
	if (!ret)
		ret = regmap_write(ktd->regmap, KTD3137_REG_MODE, ktd->mode);
	if (ret)
		return dev_err_probe(dev, ret, "cannot configure chip\n");

	/* Start from what the bootloader left, so the screen does not flash. */
	if (!regmap_read(ktd->regmap, KTD3137_REG_RATIO_LSB, &lsb) &&
	    !regmap_read(ktd->regmap, KTD3137_REG_RATIO_MSB, &msb)) {
		unsigned int level = (msb << 3) | (lsb & 0x07);

		if (level)
			props.brightness = level;
	}
	of_property_read_u32(dev->of_node, "default-brightness", &props.brightness);
	if (props.brightness > KTD3137_MAX_BRIGHTNESS)
		props.brightness = KTD3137_MAX_BRIGHTNESS;

	bl = devm_backlight_device_register(dev, dev_name(dev), dev, ktd,
					    &ktd3137_bl_ops, &props);
	if (IS_ERR(bl))
		return dev_err_probe(dev, PTR_ERR(bl), "cannot register backlight\n");

	i2c_set_clientdata(client, bl);

	ret = backlight_update_status(bl);
	if (ret)
		return dev_err_probe(dev, ret, "cannot set brightness\n");

	dev_info(dev, "KTD3137 backlight, brightness %d/%d\n",
		 props.brightness, KTD3137_MAX_BRIGHTNESS);
	return 0;
}

static void ktd3137_shutdown(struct i2c_client *client)
{
	struct backlight_device *bl = i2c_get_clientdata(client);

	if (bl)
		ktd3137_write_brightness(bl_get_data(bl), 0);
}

static const struct of_device_id ktd3137_of_match[] = {
	{ .compatible = "kinetic,ktd3137" },
	{ }
};
MODULE_DEVICE_TABLE(of, ktd3137_of_match);

static const struct i2c_device_id ktd3137_ids[] = {
	{ "ktd3137" },
	{ }
};
MODULE_DEVICE_TABLE(i2c, ktd3137_ids);

static struct i2c_driver ktd3137_driver = {
	.driver = {
		.name = "ktd3137-backlight",
		.of_match_table = ktd3137_of_match,
	},
	.probe = ktd3137_probe,
	.shutdown = ktd3137_shutdown,
	.id_table = ktd3137_ids,
};
module_i2c_driver(ktd3137_driver);

MODULE_DESCRIPTION("Kinetic KTD3137 backlight driver");
MODULE_LICENSE("GPL");
