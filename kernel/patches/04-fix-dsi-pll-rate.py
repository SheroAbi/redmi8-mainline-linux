#!/usr/bin/env python3
#!/usr/bin/env python3
"""Step 04: decode the 12 nm PLL fractional (SSC) registers in recalc_rate.

    python3 04-fix-dsi-pll-rate.py <kernel-tree>
"""
from pathlib import Path
from math import gcd
import sys

if len(sys.argv) != 2:
    sys.exit(__doc__)
tree = Path(sys.argv[1])
p = tree / 'drivers/gpu/drm/msm/dsi/phy/dsi_phy_12nm.c'
s = p.read_text()
start = s.index('static unsigned long dsi_pll_12nm_clk_recalc_rate(')
end = s.index('static int dsi_pll_12nm_vco_prepare(', start)
s = s[:start] + '''static unsigned long dsi_pll_12nm_clk_recalc_rate(struct clk_hw *hw,
					unsigned long parent_rate)
{
	struct dsi_pll_12nm *pll_12nm = to_pll_12nm(hw);
	void __iomem *base = pll_12nm->phy->pll_base;
	u32 mint, quot, rem, den;
	u64 rate, numerator, denominator;

	/* SSC contains the fractional part omitted by LOOP_DIV_RATIO. Reading
	 * only that integer divider loses up to 4.8 MHz and makes the GCC pixel
	 * clock reject a valid DSI clock ratio. Decode what was programmed, not
	 * the clock framework's potentially stale cached rate.
	 */
	den = (readl(base + DSIPHY_SSC14) & 0xff) |
		((readl(base + DSIPHY_SSC15) & 0xff) << 8);
	if ((readl(base + DSIPHY_SSC0) & BIT(0)) && den) {
		mint = (readl(base + DSIPHY_SSC7) & 0xff) |
			((readl(base + DSIPHY_SSC8) & 0xff) << 8);
		quot = (readl(base + DSIPHY_SSC10) & 0xff) |
			((readl(base + DSIPHY_SSC11) & 0xff) << 8);
		rem = (readl(base + DSIPHY_SSC12) & 0xff) |
			((readl(base + DSIPHY_SSC13) & 0xff) << 8);
		rate = (u64)VCO_REF_CLK_RATE * (mint + 32) / 4;
		numerator = (u64)VCO_REF_CLK_RATE * ((u64)quot * den + rem);
		denominator = (u64)131072 * den;
		return rate + div64_u64(numerator + denominator / 2, denominator);
	}

	mint = (readl(base + DSIPHY_PLL_LOOP_DIV_RATIO_0) & 0x3f) |
		((readl(base + DSIPHY_PLL_LOOP_DIV_RATIO_1) & 0x3f) << 6);
	return (u64)VCO_REF_CLK_RATE * mint / 4;
}

''' + s[end:]
p.write_text(s)

# Round-trip the independently documented encoding at the actual panel rate,
# at integral reference multiples, and near quarter-reference boundaries.
ref = 19_200_000
for rate in (1_031_676_000, 1_000_000_000, 1_027_200_000,
             1_027_200_001, 1_031_999_999, 1_200_000_000, 2_000_000_000):
    integer, fractional = divmod(rate, ref // 4)
    den = ref // gcd(rate, ref)
    quot, remainder = divmod(fractional * 131072, ref)
    rem = remainder * den // ref
    # Current panel rate is exactly representable in the 16-bit denominator.
    if den > 65535:
        continue
    numerator = ref * (quot * den + rem)
    denominator = 131072 * den
    decoded = ref * integer // 4 + (numerator + denominator // 2) // denominator
    assert decoded == rate, (rate, decoded)
    if rate == 1_031_676_000:
        assert (integer - 32, quot, rem, den) == (182, 30556, 256, 1600)
        print(f'Panel PLL exact: {decoded} Hz; pixel /12 = {decoded // 12} Hz')

p = tree / 'drivers/input/touchscreen/ili9881h-tddi.c'
s = p.read_text()
needle = '\treturn -ETIMEDOUT;\n}\n\nstatic u8 ili_checksum'
replacement = '\tdev_err(&ts->spi->dev, "Firmware TX handshake timed out: %*ph\\n", 4, rx);\n' + needle
if replacement not in s:
    assert s.count(needle) == 1
    p.write_text(s.replace(needle, replacement, 1))
