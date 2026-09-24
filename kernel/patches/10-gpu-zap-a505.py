#!/usr/bin/env python3
"""Step 10: final GPU fix for the Redmi 8 (olive, SDM439, Adreno 505).

    python3 10-gpu-zap-a505.py <kernel-tree>

1. A505 has CPZ retention like A506 (stock Xiaomi kernel: A505 feature word
   0x660 == A506, i.e. CONTENT_PROTECTION|PREEMPTION|64BIT|CPZ_RETENTION).
   The zap resume SCM call hard-resets the SoC on every GPU runtime resume.
2. Remove the temporary A505 diagnostics added during bring-up.
3. DTS: stock a506_zap via TZ (PAS 13) and a ramoops region (stock pstore
   address) so crashes leave a log.
"""
from pathlib import Path
import sys

if len(sys.argv) != 2:
    sys.exit(__doc__)
T = Path(sys.argv[1])


def edit(rel, old, new, count=1):
    p = T / rel
    s = p.read_text()
    assert s.count(old) == count, (rel, old[:60], s.count(old))
    p.write_text(s.replace(old, new))


def undo_diag(rel, old, new):
    """Remove a bring-up diagnostic; a clean replay never had it."""
    p = T / rel
    s = p.read_text()
    if old in s:
        p.write_text(s.replace(old, new, 1))


a5 = 'drivers/gpu/drm/msm/adreno/a5xx_gpu.c'
edit(a5, '''	/*
	 * Adreno 506 have CPZ Retention feature and doesn't require
	 * to resume zap shader
	 */
	if (adreno_is_a506(adreno_gpu))
		return 0;
''', '''	/*
	 * Adreno 505 and 506 have CPZ Retention feature and don't require
	 * to resume zap shader. On SDM439 the resume call resets the SoC.
	 */
	if (adreno_is_a505(adreno_gpu) || adreno_is_a506(adreno_gpu))
		return 0;
''')
undo_diag(a5, '''static bool a505_single_ring;
module_param(a505_single_ring, bool, 0400);
MODULE_PARM_DESC(a505_single_ring, "Diagnose A505 rendering without hardware queue preemption");

''', '')
undo_diag(a5, '''	if (config->info->revn == 510 ||
	    (config->info->revn == 505 && a505_single_ring))
		nr_rings = 1;''', '''	if (config->info->revn == 510)
		nr_rings = 1;''')
undo_diag(a5, '''static bool a505_no_hwcg;
module_param(a505_no_hwcg, bool, 0600);
MODULE_PARM_DESC(a505_no_hwcg, "Temporary A505 HW clock gating diagnostic");

''', '')
undo_diag(a5, '''	if (adreno_is_a505(adreno_gpu) && a505_no_hwcg)
		state = false;

''', '')

ag = 'drivers/gpu/drm/msm/adreno/adreno_gpu.c'
undo_diag(ag, '''static ulong a505_test_va_start;
module_param(a505_test_va_start, ulong, 0400);
MODULE_PARM_DESC(a505_test_va_start, "Temporary A505 lower GPU VA bound diagnostic");

''', '')
undo_diag(ag, '''	if (to_adreno_gpu(gpu)->info->revn == 505 && a505_test_va_start &&
	    a505_test_va_start < geometry->aperture_end)
		start = max_t(u64, start, a505_test_va_start);
''', '')

undo_diag('drivers/gpu/drm/msm/msm_ringbuffer.c', '''	{
		static unsigned int diagnostic_submits;
		if (diagnostic_submits++ < 16)
			dev_info(gpu->dev->dev,
				 "Olive submit ring=%d commands=%u closed=%u seq=%llu\\n",
				 submit->ring->id, submit->nr_cmds,
				 submit->queue->ctx->closed, submit->hw_fence->seqno);
	}

''', '')

dts = 'arch/arm64/boot/dts/qcom/sdm439-xiaomi-olive.dts'
edit(dts, '''	reserved-memory {
''', '''	reserved-memory {
		gpu_zap_mem: gpu-zap {
			size = <0x0 0x100000>;
			alignment = <0x0 0x100000>;
			alloc-ranges = <0x0 0x80000000 0x0 0x10000000>;
			no-map;
		};

		/* Same region as the stock pstore reservation. */
		ramoops@9ff00000 {
			compatible = "ramoops";
			reg = <0x0 0x9ff00000 0x0 0x100000>;
			record-size = <0x20000>;
			console-size = <0x40000>;
			pmsg-size = <0x20000>;
			no-map;
		};

''')
edit(dts, '''&gpu {
	status = "okay";
};''', '''&gpu {
	status = "okay";

	/* Stock vendor firmware, loaded by TZ as PAS 13 like qcom,kgsl-hyp. */
	zap-shader {
		memory-region = <&gpu_zap_mem>;
		firmware-name = "qcom/sdm439/xiaomi/olive/a506_zap.mdt";
	};
};''')

for rel in (a5, ag, 'drivers/gpu/drm/msm/msm_ringbuffer.c'):
    s = (T / rel).read_text()
    assert 'a505_single_ring' not in s and 'a505_no_hwcg' not in s
    assert 'a505_test_va_start' not in s and 'Olive submit' not in s
print('patched')
