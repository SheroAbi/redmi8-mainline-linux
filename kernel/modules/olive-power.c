// SPDX-License-Identifier: GPL-2.0-only
/*
 * Redmi 8 (olive) battery and USB input reporting for the PMI632.
 *
 * The PMI632 carries an SMB5 charger (0x1000) and a QGauge (0x4800). Mainline
 * has drivers for neither. The charger keeps running on the configuration the
 * bootloader left, so this driver does not write a single PMIC register: it
 * only reports, so that GNOME/UPower can show the battery and the cable.
 *
 * Register layout from the SMB5/QG drivers used on the Mi 9T (PM8150B, same
 * SMB5 and QG generation): qcom_smbx.c and qcom_qg.c of the sm7150-mainline
 * tree, as patched in the Mi 9T port (github.com/SheroAbi/mi9t-mainline-linux).
 * The state of charge follows qcom_qg.c: seed from the open-circuit voltage,
 * then integrate the gauge current.
 */

#include <linux/devm-helpers.h>
#include <linux/iio/consumer.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/power_supply.h>
#include <linux/regmap.h>
#include <linux/timekeeping.h>
#include <linux/workqueue.h>

/* SMB5 charger, relative to the charger base (0x1000) */
#define BATTERY_CHARGER_STATUS_1	0x06
#define BATTERY_CHARGER_STATUS_MASK	GENMASK(2, 0)
#define BATTERY_CHARGER_STATUS_2	0x07
#define SMB5_BAT_OV_BIT			BIT(1)
#define ICL_STATUS			0x107
#define POWER_PATH_STATUS		0x10b
#define P_PATH_USE_USBIN_BIT		BIT(4)
#define P_PATH_VALID_INPUT_BIT		BIT(0)
#define APSD_STATUS			0x307
#define APSD_DONE_BIT			BIT(0)
#define APSD_RESULT_STATUS		0x308
#define FLOAT_CHARGER_BIT		BIT(4)
#define DCP_CHARGER_BIT			BIT(3)
#define CDP_CHARGER_BIT			BIT(2)
#define OCP_CHARGER_BIT			BIT(1)
#define FLOAT_VOLTAGE_CFG		0x70
#define FAST_CHARGE_CURRENT_CFG		0x61

/* QGauge, relative to the QG base (0x4800) */
#define QG_PON_V			0x70
#define QG_PON_I			0x72
#define QG_S2_AVG_V			0x80
#define QG_S2_AVG_I			0x82
#define QG_LAST_ADC_V			0xc0
#define QG_LAST_ADC_I			0xc2

#define OLIVE_DESIGN_UAH		5000000
#define OLIVE_VMAX_UV			4400000
#define OLIVE_VMIN_UV			3400000
#define CURRENT_IDLE_UA			30000

struct olive_power {
	struct device *dev;
	struct regmap *regmap;
	u32 chg, qg;
	struct iio_channel *usbin_v, *usbin_i, *vbat, *therm;
	struct power_supply *usb, *batt;
	struct mutex lock;
	int soc_permille;	/* -1 until seeded */
	u64 sample_ms;
	s64 charge_uams, full_uams;
	bool qg_ok;
	int float_permille;	/* 4.4 V-curve SOC at the charger float voltage */
	int last_online;
	struct delayed_work work;
};

/* OCV (uV) -> SOC (permille) for a 4.4 V Li-ion cell, as in qcom_qg.c */
static const struct { int uv, pm; } ocv_curve[] = {
	{ 3400000,    0 }, { 3500000,   30 }, { 3570000,   70 },
	{ 3620000,  120 }, { 3660000,  180 }, { 3700000,  250 },
	{ 3730000,  320 }, { 3760000,  390 }, { 3800000,  460 },
	{ 3850000,  530 }, { 3900000,  600 }, { 3960000,  670 },
	{ 4020000,  740 }, { 4080000,  810 }, { 4150000,  880 },
	{ 4230000,  940 }, { 4310000,  980 }, { 4400000, 1000 },
};

static int ocv_to_permille(int uv)
{
	int i, n = ARRAY_SIZE(ocv_curve);

	if (uv <= ocv_curve[0].uv)
		return 0;
	for (i = 1; i < n; i++)
		if (uv < ocv_curve[i].uv)
			return ocv_curve[i - 1].pm +
			       DIV_ROUND_CLOSEST((uv - ocv_curve[i - 1].uv) *
						 (ocv_curve[i].pm - ocv_curve[i - 1].pm),
						 ocv_curve[i].uv - ocv_curve[i - 1].uv);
	return 1000;
}

/* The charger stops at its float voltage: that point is 100 %. */
static int soc_permille(struct olive_power *op, int ocv_uv)
{
	int pm = ocv_to_permille(ocv_uv);

	if (op->float_permille > 0 && op->float_permille < 1000)
		pm = DIV_ROUND_CLOSEST(pm * 1000, op->float_permille);
	return min(pm, 1000);
}

static int qg_read16(struct olive_power *op, u8 off, u16 *val)
{
	u8 b[2];
	int ret = regmap_bulk_read(op->regmap, op->qg + off, b, 2);

	if (!ret)
		*val = b[1] << 8 | b[0];
	return ret;
}

static int qg_voltage(struct olive_power *op, u8 off, int *uv)
{
	u16 raw;
	int ret = qg_read16(op, off, &raw);

	if (!ret)
		*uv = div_u64((u64)raw * 194637, 1000);
	return ret;
}

/* Positive = into the battery (charging), as the power-supply ABI wants. */
static int qg_current(struct olive_power *op, u8 off, int *ua)
{
	u16 raw;
	int ret = qg_read16(op, off, &raw);

	if (ret)
		return ret;
	/* 0x8000 is what an average register holds before its first sample. */
	if (raw == 0x8000)
		return -ENODATA;
	*ua = -(int)div_s64((s64)(s16)raw * 152588, 1000);
	return 0;
}

static int batt_voltage(struct olive_power *op, int *uv)
{
	int ret;

	if (op->qg_ok && !qg_voltage(op, QG_LAST_ADC_V, uv) &&
	    *uv > 2500000 && *uv < 4600000)
		return 0;
	ret = iio_read_channel_processed(op->vbat, uv);
	return ret < 0 ? ret : 0;
}

static int batt_current(struct olive_power *op, u8 off, int *ua)
{
	if (!op->qg_ok)
		return -ENODATA;
	return qg_current(op, off, ua);
}

static int usb_online(struct olive_power *op)
{
	unsigned int stat;

	if (regmap_read(op->regmap, op->chg + POWER_PATH_STATUS, &stat))
		return 0;
	return (stat & P_PATH_USE_USBIN_BIT) && (stat & P_PATH_VALID_INPUT_BIT);
}

static int batt_status(struct olive_power *op)
{
	unsigned int stat, stat2;

	if (!usb_online(op))
		return POWER_SUPPLY_STATUS_DISCHARGING;
	if (regmap_read(op->regmap, op->chg + BATTERY_CHARGER_STATUS_1, &stat) ||
	    regmap_read(op->regmap, op->chg + BATTERY_CHARGER_STATUS_2, &stat2))
		return POWER_SUPPLY_STATUS_UNKNOWN;
	if (stat2 & SMB5_BAT_OV_BIT)
		return POWER_SUPPLY_STATUS_NOT_CHARGING;
	switch (stat & BATTERY_CHARGER_STATUS_MASK) {
	case 0: /* INHIBIT */
	case 5: /* TERMINATE */
		return POWER_SUPPLY_STATUS_FULL;
	case 1: /* TRICKLE */
	case 2: /* PRE */
	case 3: /* FULLON */
	case 4: /* TAPER */
		return POWER_SUPPLY_STATUS_CHARGING;
	default: /* PAUSE, DISABLE */
		return POWER_SUPPLY_STATUS_NOT_CHARGING;
	}
}

/* Called with op->lock held. */
static void update_soc(struct olive_power *op)
{
	u64 now = ktime_to_ms(ktime_get_boottime());
	int uv, ua = 0, status;

	if (op->soc_permille >= 0 && now - op->sample_ms < 1000)
		return;
	if (batt_voltage(op, &uv))
		return;
	if (batt_current(op, QG_LAST_ADC_I, &ua) || abs(ua) > 6000000)
		ua = 0;

	if (op->soc_permille < 0) {
		/* ~120 mOhm cell + path: estimate the open-circuit voltage */
		int ocv = uv - div_s64((s64)ua * 120, 1000);

		op->full_uams = (s64)OLIVE_DESIGN_UAH * 3600000;
		op->soc_permille = clamp(soc_permille(op, ocv), 0, 990);
		op->charge_uams = div_s64(op->full_uams * op->soc_permille, 1000);
		dev_info(op->dev, "battery %d uV, %d uA, OCV %d uV -> %d.%d %%\n",
			 uv, ua, ocv, op->soc_permille / 10, op->soc_permille % 10);
	} else if (op->qg_ok) {
		u64 elapsed = min_t(u64, now - op->sample_ms, 24ULL * 3600 * 1000);

		op->charge_uams += (s64)ua * (s64)elapsed;
	} else {
		/* No gauge current: follow the voltage, slowly. */
		int target = soc_permille(op, uv) * 1000;
		s64 cur = div_s64(op->charge_uams * 1000000, op->full_uams);

		op->charge_uams = div_s64(op->full_uams * div_s64(cur * 15 + target, 16), 1000000);
	}

	status = batt_status(op);
	if (status == POWER_SUPPLY_STATUS_FULL)
		op->charge_uams = op->full_uams;
	else if (status == POWER_SUPPLY_STATUS_CHARGING)
		op->charge_uams = min_t(s64, op->charge_uams, div_s64(op->full_uams * 99, 100));
	if (uv < 3350000 && ua < 0)
		op->charge_uams = min_t(s64, op->charge_uams, div_s64(op->full_uams, 100));
	op->charge_uams = clamp_t(s64, op->charge_uams, 0, op->full_uams);
	op->sample_ms = now;
}

static int capacity(struct olive_power *op)
{
	int cap;

	mutex_lock(&op->lock);
	update_soc(op);
	cap = op->full_uams ? div64_s64(op->charge_uams * 100 + op->full_uams / 2,
					  op->full_uams) : 50;
	mutex_unlock(&op->lock);
	return clamp(cap, 0, 100);
}

static enum power_supply_property batt_props[] = {
	POWER_SUPPLY_PROP_STATUS,
	POWER_SUPPLY_PROP_PRESENT,
	POWER_SUPPLY_PROP_TECHNOLOGY,
	POWER_SUPPLY_PROP_CAPACITY,
	POWER_SUPPLY_PROP_VOLTAGE_NOW,
	POWER_SUPPLY_PROP_VOLTAGE_AVG,
	POWER_SUPPLY_PROP_CURRENT_NOW,
	POWER_SUPPLY_PROP_CURRENT_AVG,
	POWER_SUPPLY_PROP_VOLTAGE_MAX_DESIGN,
	POWER_SUPPLY_PROP_VOLTAGE_MIN_DESIGN,
	POWER_SUPPLY_PROP_CHARGE_FULL_DESIGN,
	POWER_SUPPLY_PROP_CHARGE_FULL,
	POWER_SUPPLY_PROP_CHARGE_NOW,
	POWER_SUPPLY_PROP_TEMP,
	POWER_SUPPLY_PROP_SCOPE,
};

static int batt_get(struct power_supply *psy, enum power_supply_property psp,
		    union power_supply_propval *val)
{
	struct olive_power *op = power_supply_get_drvdata(psy);
	int ret;

	switch (psp) {
	case POWER_SUPPLY_PROP_STATUS:
		val->intval = batt_status(op);
		return 0;
	case POWER_SUPPLY_PROP_PRESENT:
		val->intval = 1;
		return 0;
	case POWER_SUPPLY_PROP_TECHNOLOGY:
		val->intval = POWER_SUPPLY_TECHNOLOGY_LION;
		return 0;
	case POWER_SUPPLY_PROP_CAPACITY:
		val->intval = capacity(op);
		return 0;
	case POWER_SUPPLY_PROP_VOLTAGE_NOW:
		return batt_voltage(op, &val->intval);
	case POWER_SUPPLY_PROP_VOLTAGE_AVG:
		if (op->qg_ok && !qg_voltage(op, QG_S2_AVG_V, &val->intval) &&
		    val->intval > 2500000 && val->intval < 4600000)
			return 0;
		return batt_voltage(op, &val->intval);
	case POWER_SUPPLY_PROP_CURRENT_NOW:
		return batt_current(op, QG_LAST_ADC_I, &val->intval);
	case POWER_SUPPLY_PROP_CURRENT_AVG:
		return batt_current(op, QG_S2_AVG_I, &val->intval);
	case POWER_SUPPLY_PROP_VOLTAGE_MAX_DESIGN:
		val->intval = OLIVE_VMAX_UV;
		return 0;
	case POWER_SUPPLY_PROP_VOLTAGE_MIN_DESIGN:
		val->intval = OLIVE_VMIN_UV;
		return 0;
	case POWER_SUPPLY_PROP_CHARGE_FULL_DESIGN:
	case POWER_SUPPLY_PROP_CHARGE_FULL:
		val->intval = OLIVE_DESIGN_UAH;
		return 0;
	case POWER_SUPPLY_PROP_CHARGE_NOW:
		val->intval = div_s64((s64)OLIVE_DESIGN_UAH * capacity(op), 100);
		return 0;
	case POWER_SUPPLY_PROP_TEMP:
		if (!op->therm)
			return -ENODATA;
		ret = iio_read_channel_processed(op->therm, &val->intval);
		if (ret < 0)
			return ret;
		val->intval /= 100; /* milli-degC -> deci-degC */
		return 0;
	case POWER_SUPPLY_PROP_SCOPE:
		val->intval = POWER_SUPPLY_SCOPE_SYSTEM;
		return 0;
	default:
		return -EINVAL;
	}
}

static enum power_supply_property usb_props[] = {
	POWER_SUPPLY_PROP_ONLINE,
	POWER_SUPPLY_PROP_VOLTAGE_NOW,
	POWER_SUPPLY_PROP_CURRENT_NOW,
	POWER_SUPPLY_PROP_INPUT_CURRENT_LIMIT,
	POWER_SUPPLY_PROP_USB_TYPE,
};

static int usb_get(struct power_supply *psy, enum power_supply_property psp,
		   union power_supply_propval *val)
{
	struct olive_power *op = power_supply_get_drvdata(psy);
	unsigned int stat;
	int ret;

	switch (psp) {
	case POWER_SUPPLY_PROP_ONLINE:
		val->intval = usb_online(op);
		return 0;
	case POWER_SUPPLY_PROP_VOLTAGE_NOW:
		ret = iio_read_channel_processed(op->usbin_v, &val->intval);
		return ret < 0 ? ret : 0;
	case POWER_SUPPLY_PROP_CURRENT_NOW:
		if (!usb_online(op)) {
			val->intval = 0;
			return 0;
		}
		ret = iio_read_channel_processed(op->usbin_i, &val->intval);
		if (ret < 0)
			return ret;
		/* PMI632 USBIN current sense: 0.4 V/A in buck mode */
		val->intval = DIV_ROUND_CLOSEST(val->intval * 100, 40);
		return 0;
	case POWER_SUPPLY_PROP_INPUT_CURRENT_LIMIT:
		ret = regmap_read(op->regmap, op->chg + ICL_STATUS, &stat);
		if (ret)
			return ret;
		val->intval = stat * 50000;
		return 0;
	case POWER_SUPPLY_PROP_USB_TYPE:
		val->intval = POWER_SUPPLY_USB_TYPE_UNKNOWN;
		if (!usb_online(op) ||
		    regmap_read(op->regmap, op->chg + APSD_STATUS, &stat) ||
		    !(stat & APSD_DONE_BIT) ||
		    regmap_read(op->regmap, op->chg + APSD_RESULT_STATUS, &stat))
			return 0;
		if (stat & CDP_CHARGER_BIT)
			val->intval = POWER_SUPPLY_USB_TYPE_CDP;
		else if (stat & (DCP_CHARGER_BIT | OCP_CHARGER_BIT | FLOAT_CHARGER_BIT))
			val->intval = POWER_SUPPLY_USB_TYPE_DCP;
		else
			val->intval = POWER_SUPPLY_USB_TYPE_SDP;
		return 0;
	default:
		return -EINVAL;
	}
}

static const struct power_supply_desc batt_desc = {
	.name = "battery",
	.type = POWER_SUPPLY_TYPE_BATTERY,
	.properties = batt_props,
	.num_properties = ARRAY_SIZE(batt_props),
	.get_property = batt_get,
};

static const struct power_supply_desc usb_desc = {
	.name = "usb",
	.type = POWER_SUPPLY_TYPE_USB,
	.usb_types = BIT(POWER_SUPPLY_USB_TYPE_SDP) | BIT(POWER_SUPPLY_USB_TYPE_CDP) |
		     BIT(POWER_SUPPLY_USB_TYPE_DCP) | BIT(POWER_SUPPLY_USB_TYPE_UNKNOWN),
	.properties = usb_props,
	.num_properties = ARRAY_SIZE(usb_props),
	.get_property = usb_get,
};

/* No charger IRQs are requested; poll so UPower sees plug/unplug and levels. */
static void olive_power_work(struct work_struct *work)
{
	struct olive_power *op = container_of(to_delayed_work(work), struct olive_power, work);
	int online = usb_online(op);

	capacity(op);
	if (online != op->last_online) {
		op->last_online = online;
		power_supply_changed(op->usb);
	}
	power_supply_changed(op->batt);
	schedule_delayed_work(&op->work, msecs_to_jiffies(5000));
}

static char *olive_supplied_to[] = { "battery" };

static int olive_power_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct power_supply_config cfg = {};
	struct olive_power *op;
	unsigned int fv = 0, fcc = 0;
	int uv_qg = 0, uv_adc = 0, ua = 0;
	int ret;

	op = devm_kzalloc(dev, sizeof(*op), GFP_KERNEL);
	if (!op)
		return -ENOMEM;
	op->dev = dev;
	op->soc_permille = -1;
	op->last_online = -1;
	mutex_init(&op->lock);

	op->regmap = dev_get_regmap(dev->parent, NULL);
	if (!op->regmap)
		return dev_err_probe(dev, -ENODEV, "no PMIC regmap\n");
	if (device_property_read_u32(dev, "reg", &op->chg))
		return dev_err_probe(dev, -EINVAL, "no charger base\n");
	if (device_property_read_u32(dev, "qcom,qg-base", &op->qg))
		op->qg = 0x4800;

	op->usbin_v = devm_iio_channel_get(dev, "usbin_v");
	if (IS_ERR(op->usbin_v))
		return dev_err_probe(dev, PTR_ERR(op->usbin_v), "usbin_v\n");
	op->usbin_i = devm_iio_channel_get(dev, "usbin_i");
	if (IS_ERR(op->usbin_i))
		return dev_err_probe(dev, PTR_ERR(op->usbin_i), "usbin_i\n");
	op->vbat = devm_iio_channel_get(dev, "vbat");
	if (IS_ERR(op->vbat))
		return dev_err_probe(dev, PTR_ERR(op->vbat), "vbat\n");
	op->therm = devm_iio_channel_get(dev, "batt_therm");
	if (IS_ERR(op->therm))
		op->therm = NULL;

	/* Trust the gauge only if it agrees with the independent ADC. */
	ret = iio_read_channel_processed(op->vbat, &uv_adc);
	if (ret >= 0 && !qg_voltage(op, QG_LAST_ADC_V, &uv_qg) &&
	    !qg_current(op, QG_LAST_ADC_I, &ua))
		op->qg_ok = abs(uv_qg - uv_adc) < 150000 && abs(ua) < 6000000;
	regmap_read(op->regmap, op->chg + FLOAT_VOLTAGE_CFG, &fv);
	regmap_read(op->regmap, op->chg + FAST_CHARGE_CURRENT_CFG, &fcc);
	if (fv > 0 && fv <= 80)
		op->float_permille = ocv_to_permille((3600 + fv * 10) * 1000 - 20000);
	dev_info(dev, "vbat adc %d uV, gauge %d uV %d uA (%s); float %u mV, fcc %u mA, usb %d\n",
		 uv_adc, uv_qg, ua, op->qg_ok ? "used" : "ignored",
		 3600 + fv * 10, fcc * 50, usb_online(op));

	cfg.drv_data = op;
	cfg.fwnode = dev_fwnode(dev);
	op->batt = devm_power_supply_register(dev, &batt_desc, &cfg);
	if (IS_ERR(op->batt))
		return dev_err_probe(dev, PTR_ERR(op->batt), "battery psy\n");
	cfg.supplied_to = olive_supplied_to;
	cfg.num_supplicants = ARRAY_SIZE(olive_supplied_to);
	op->usb = devm_power_supply_register(dev, &usb_desc, &cfg);
	if (IS_ERR(op->usb))
		return dev_err_probe(dev, PTR_ERR(op->usb), "usb psy\n");

	ret = devm_delayed_work_autocancel(dev, &op->work, olive_power_work);
	if (ret)
		return ret;
	schedule_delayed_work(&op->work, msecs_to_jiffies(2000));
	return 0;
}

static const struct of_device_id olive_power_of_match[] = {
	{ .compatible = "xiaomi,olive-power" },
	{ }
};
MODULE_DEVICE_TABLE(of, olive_power_of_match);

static struct platform_driver olive_power_driver = {
	.probe = olive_power_probe,
	.driver = {
		.name = "olive-power",
		.of_match_table = olive_power_of_match,
	},
};
module_platform_driver(olive_power_driver);

MODULE_DESCRIPTION("Redmi 8 PMI632 battery and USB input reporting (read-only)");
MODULE_LICENSE("GPL");
