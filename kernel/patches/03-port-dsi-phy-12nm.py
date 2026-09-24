#!/usr/bin/env python3
"""Step 03: port the SDM439 12 nm DSI PHY driver.

    python3 03-port-dsi-phy-12nm.py <kernel-tree>

Source: sdm439-12nm/ (msm89x7-mainline/linux experiment branch,
ce300c988d766c23c56a0fb1705b652bfd6b5fde), adapted to Linux 7.1: panel PHY
timings from the device tree, determine_rate instead of round_rate, and the
register save/restore order fixed. Also sets LOCALVERSION=-msm89x7-olive-r7.
"""
from pathlib import Path
import re
import subprocess
import sys

if len(sys.argv) != 2:
    sys.exit(__doc__)
tree = Path(sys.argv[1])
reference = Path(__file__).resolve().parent / 'sdm439-12nm'
phy_path = 'drivers/gpu/drm/msm/dsi/phy/dsi_phy_12nm.c'

def change(path, old, new):
    p = tree / path
    s = p.read_text()
    assert s.count(old) == 1, (path, old, s.count(old))
    p.write_text(s.replace(old, new, 1))

s = (reference / phy_path).read_text()
# Keep actual errors, demote temporary bring-up logging.
for line in s.splitlines():
    if 'pr_err(' in line and 'lock failed' not in line and 'index not found' not in line:
        s = s.replace(line, line.replace('pr_err(', 'pr_debug('))
s = s.replace('bool pll_locked;', 'bool pll_locked = false;')
s = s.replace('char data = 0;', 'u32 data = 0;')
# clk_hw_get_rate returns the cached rate: using it in recalc hides rate changes.
s = s.replace('\tunsigned long vco_current_rate = clk_hw_get_rate(hw);\n', '')
s = s.replace('\n\tif (vco_current_rate != 0) {\n\t\treturn vco_current_rate;\n\t}\n', '\n')
# /2 is encoded by VCO_CTRL 0x30 plus CPBIAS bit 6, not /4.
s = s.replace('if (vco_cntrl == 0x30)\n\t\t\tpost_div_mux = 2;',
              'if (vco_cntrl == 0x30)\n\t\t\tpost_div_mux = 1;')
s = s.replace('if (vco_cntrl == 0x30)\n\t\t\tval = 2;',
              'if (vco_cntrl == 0x30)\n\t\t\tval = 1;')
# Restore the same registers that were saved, in the matching order.
s = s.replace('writel(cached_state->postdiv3, base + DSIPHY_PLL_CTRL);',
              'writel(cached_state->postdiv1, base + DSIPHY_PLL_CTRL);')
s = s.replace('writel(cached_state->postdiv1, base + DSIPHY_SSC9);',
              'writel(cached_state->postdiv3, base + DSIPHY_SSC9);')
s = s.replace('\tpll_12nm->phy = phy;\n',
              '\tpll_12nm->phy = phy;\n\tspin_lock_init(&pll_12nm->postdiv_lock);\n\tspin_lock_init(&pll_12nm->gpdiv_lock);\n')
s = re.sub(r'\tlong long rate = clk_hw_get_rate\(phy->vco_hw\);\n\tpr_debug\("vco rate = %lld\\n", rate\);\n', '', s)
# Unused custom pixel divider was superseded by the standard divider in this branch.
start = s.index('#define div_mask(width)', s.index('static const struct clk_ops clk_ops_dsi_pll_12nm_gpdiv'))
end = s.index('/*\n * PLL Callbacks', start)
s = s[:start] + s[end:]
s = s.replace('\t.has_phy_regulator = true,\n', '')
# Use explicit panel-matched byte timings; do not transplant the branch's c3e values.
# clk_pre/post are the DSI host timings from the stock c3i panel, separate from PHY.
s = s.replace('static int dsi_12nm_phy_enable(',
              'static void mdss_dsi_12nm_phy_hstx_drv_ctrl(struct msm_dsi_phy *phy, bool enable);\n\nstatic int dsi_12nm_phy_enable(', 1)
old = '''\tstruct msm_dsi_dphy_timing *timing = &phy->timing;

\tif (msm_dsi_dphy_timing_calc_v1_2(timing, clk_req)) {
\t\tDRM_DEV_ERROR(&phy->pdev->dev,
\t\t\t      "%s: timing calculation failed\\n",
\t\t\t      __func__);
\t\treturn -EINVAL;
\t}
'''
new = '''\tstruct device *dev = &phy->pdev->dev;
\tu8 timing[8];
\tint ret;

\tif (!clk_req->bitclk_rate || !clk_req->escclk_rate)
\t\treturn -EINVAL;
\tret = of_property_read_u8_array(dev->of_node,
\t\t\t"qcom,phy-timings", timing, sizeof(timing));
\tif (ret)
\t\treturn dev_err_probe(dev, ret, "Panel-specific 12nm PHY timings missing\\n");
\tphy->timing.shared_timings.clk_pre = 0x06;
\tphy->timing.shared_timings.clk_post = 0x60;
\tphy->timing.shared_timings.clk_pre_inc_by_2 = false;
'''
assert old in s
s = s.replace(old, new, 1)
for name, index in {'clk_zero':0, 'clk_trail':1, 'clk_post':2, 'clk_rqst':3,
                    'hs_zero':4, 'hs_trail':5, 'hs_rqst':6, 'hs_exit':7}.items():
    s = s.replace('timing->' + name, f'timing[{index}]')
needle = '\twritel(0x00, phy->base + HSTX_DATAREV_CTRL_CLKLANE);\n\twmb(); /* make sure DSI PHY registers are programmed */'
s = s.replace(needle, needle + '\n\tmdss_dsi_12nm_phy_hstx_drv_ctrl(phy, true);', 1)
s = s.replace('static void dsi_12nm_phy_disable(struct msm_dsi_phy *phy)\n{',
              'static void dsi_12nm_phy_disable(struct msm_dsi_phy *phy)\n{\n\tmdss_dsi_12nm_phy_hstx_drv_ctrl(phy, false);', 1)
s = s.replace('\t\t.hstx_drv_ctrl = mdss_dsi_12nm_phy_hstx_drv_ctrl,\n', '')
# Linux 7.1 removed clk_ops.round_rate; match the current PHY drivers.
start = s.index('static long dsi_pll_12nm_clk_round_rate(')
end = s.index('static int dsi_pll_12nm_clk_enable(', start)
s = s[:start] + '''static int dsi_pll_12nm_clk_determine_rate(struct clk_hw *hw,
\t\t\t\t\t    struct clk_rate_request *req)
{
\tstruct dsi_pll_12nm *pll_12nm = to_pll_12nm(hw);

\treq->rate = clamp_t(unsigned long, req->rate,
\t\t\t    pll_12nm->phy->cfg->min_pll_rate,
\t\t\t    pll_12nm->phy->cfg->max_pll_rate);
\treturn 0;
}

''' + s[end:]
s = s.replace('.round_rate = dsi_pll_12nm_clk_round_rate,',
              '.determine_rate = dsi_pll_12nm_clk_determine_rate,')
(tree / phy_path).write_text(s)
change('drivers/gpu/drm/msm/dsi/phy/dsi_phy.h',
       'extern const struct msm_dsi_phy_cfg dsi_phy_10nm_cfgs;',
       'extern const struct msm_dsi_phy_cfg dsi_phy_12nm_cfgs;\nextern const struct msm_dsi_phy_cfg dsi_phy_10nm_cfgs;')
change('drivers/gpu/drm/msm/dsi/phy/dsi_phy.c', '#ifdef CONFIG_DRM_MSM_DSI_10NM_PHY',
       '#ifdef CONFIG_DRM_MSM_DSI_12NM_PHY\n\t{ .compatible = "qcom,dsi-phy-12nm",\n\t  .data = &dsi_phy_12nm_cfgs },\n#endif\n#ifdef CONFIG_DRM_MSM_DSI_10NM_PHY')
change('drivers/gpu/drm/msm/Kconfig', 'config DRM_MSM_DSI_10NM_PHY',
       'config DRM_MSM_DSI_12NM_PHY\n\tbool "Enable SDM439 12nm DSI PHY"\n\tdepends on DRM_MSM_DSI\n\thelp\n\t  SDM439 PHY with explicit board timing data.\n\nconfig DRM_MSM_DSI_10NM_PHY')
change('drivers/gpu/drm/msm/Makefile',
       'msm-display-$(CONFIG_DRM_MSM_DSI_10NM_PHY) += dsi/phy/dsi_phy_10nm.o',
       'msm-display-$(CONFIG_DRM_MSM_DSI_12NM_PHY) += dsi/phy/dsi_phy_12nm.o\nmsm-display-$(CONFIG_DRM_MSM_DSI_10NM_PHY) += dsi/phy/dsi_phy_10nm.o')
p = tree / 'arch/arm64/boot/dts/qcom/sdm439.dtsi'
with p.open('a') as f:
    for num, address in ((0, '01a94400'), (1, '01a96400')):
        f.write(f'''\n&mdss_dsi{num}_phy {{
\tcompatible = "qcom,dsi-phy-12nm";
\treg = <0x{address} 0x400>, <0x{address} 0x400>;
\treg-names = "dsi_phy", "dsi_pll";
}};
''')
change('arch/arm64/boot/dts/qcom/sdm439-xiaomi-olive.dts',
       '&mdss_dsi0_phy {\n',
       '&mdss_dsi0_phy {\n\t/* Stock ili9881h c3i: 720 x 1520 at 60 Hz. */\n\tqcom,phy-timings = [0b 07 06 03 00 05 03 09];\n')
change('arch/arm64/boot/dts/qcom/sdm439-xiaomi-olive.dts',
       '\t\tspi-cpol;\n\t\tspi-cpha;\n',
       '\t\t/* Xiaomi ITK9881H uses SPI_MODE_0. */\n')
subprocess.run(['scripts/config', '--set-str', 'LOCALVERSION', '-msm89x7-olive-r7',
                '--enable', 'DRM_MSM_DSI_12NM_PHY', '--disable', 'DEBUG_INFO',
                '--disable', 'DEBUG_INFO_DWARF5', '--disable', 'DEBUG_INFO_BTF',
                '--disable', 'DEBUG_INFO_BTF_MODULES', '--enable', 'DEBUG_INFO_NONE'], cwd=tree, check=True)
print('12 nm DSI PHY ported')
