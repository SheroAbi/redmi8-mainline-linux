#!/usr/bin/env python3
"""Step 08: program the 12 nm PHY signal range from the final divider, not
from stale boot state.

    python3 08-fix-dsi-phy-range.py <kernel-tree>
"""
from pathlib import Path
import sys

if len(sys.argv) != 2:
    sys.exit(__doc__)
p = Path(sys.argv[1]) / 'drivers/gpu/drm/msm/dsi/phy/dsi_phy_12nm.c'
s=p.read_text();assert 'dsi_12nm_sync_phy_range' not in s
at=s.index('static int dsi_pll_12nm_vco_prepare(')
s=s[:at]+'''/* CCF changes the parent VCO before changing the downstream mux. */
static void dsi_12nm_sync_phy_range(struct dsi_pll_12nm *pll, u64 vco_rate)
{
	void __iomem *base = pll->phy->pll_base;
	u32 vco = readl(base + DSIPHY_PLL_VCO_CTRL) & 0x30;
	u32 bias = readl(base + DSIPHY_PLL_CHAR_PUMP_BIAS_CTRL) & BIT(6);
	u32 divider, osc;
	u64 target;

	if (!bias)
		divider = vco ? (vco >> 4) + 1 : 0;
	else
		divider = vco == 0x30 ? 1 : 5;
	target = div_u64(vco_rate, BIT(divider));
	osc = _get_osc_freq_target(target);
	writel(_get_hsfreqrange(target) | BIT(7), base + DSIPHY_HS_FREQ_RAN_SEL);
	writel(osc & 0x7f, base + DSIPHY_SLEWRATE_DDL_CYC_FRQ_ADJ_0);
	writel((osc & 0xf80) >> 7, base + DSIPHY_SLEWRATE_DDL_CYC_FRQ_ADJ_1);
	writel(_get_fsm_ovr_ctrl(target), base + DSIPHY_SLEWRATE_FSM_OVR_CTRL);
}

'''+s[at:]
needle='\tif (unlikely(pll_12nm->phy->pll_on))\n\t\treturn 0;\n'
assert s.count(needle)==1
s=s.replace(needle,needle+'''
	/* All divider choices are now committed; refresh their analogue range. */
	dsi_12nm_sync_phy_range(pll_12nm, clk_hw_get_rate(hw));
''')
needle='\twritel(data, base +  DSIPHY_PLL_CHAR_PUMP_BIAS_CTRL);\n'
assert s.count(needle)==1
s=s.replace(needle,needle+'\tdsi_12nm_sync_phy_range(pll_12nm, vco_rate);\n')
needle='\twritel(cached_state->postdiv3, base + DSIPHY_SSC9);\n'
assert s.count(needle)==1
s=s.replace(needle,needle+'\tdsi_12nm_sync_phy_range(pll_12nm, cached_state->vco_rate);\n')
p.write_text(s)
print('Signal range now follows final divider during rate changes, prepare and restore')
