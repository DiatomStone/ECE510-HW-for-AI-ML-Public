#!/usr/bin/env python3
"""
make_roofline.py — regenerate the M4 roofline figures from benchmark_data.csv.

Reusable plotting helper (kept in helper_script/). Run from anywhere:
    python3 helper_script/make_roofline.py            # all three plots
    python3 helper_script/make_roofline.py elem        # just the element-wise one
    python3 helper_script/make_roofline.py op flop     # pick any subset
(needs numpy + matplotlib)

Log-log views. `swonly` is the report §II figure (software baseline only); `op`,
`elem`, `flop` add the measured M4 x8 design; `allpts`/`allelem` show every config:

  swonly  -> report/roofline_plot.png        GFLOP/s vs FLOP/B   (software baseline only — report §II)
  flop    -> bench/roofline_flop.png         GFLOP/s vs FLOP/B   (sw baseline + x8, 9 FLOP/elem)
  op      -> bench/roofline_final.png        G OP/s  vs OP/B     (62 ops/elem, incl. PWL comparators)
  elem    -> bench/roofline_final_elem.png   G elem/s vs elem/B  (element-wise, byte-rate limited)
  allpts  -> bench/roofline_all.png          G OP/s  vs OP/B     (all configs: x1/x8/x16/x32, stream + DMA)
  allelem -> bench/roofline_all_elem.png     G elem/s vs elem/B  (all configs, element-wise)

Op convention for the hardware is the single 62-ops/elem figure (arithmetic +
PWL comparators); there is no 17-op variant here. The element-wise view needs no
op count at all — it is purely elements moved per byte.

Roofline hardware model (PCIe4 host + synthesized kernel), from benchmark.md §3 /
report §II: peak compute = 102.4 GFLOP/s, PCIe4 bandwidth = 31.5 GB/s, ridge = 3.251.
The x8 throughput is read from benchmark_data.csv so the points track the data.
"""
import csv
import os
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))      # .../m4/helper_script
ROOT = os.path.dirname(HERE)                            # .../m4
CSV = os.path.join(ROOT, "bench", "benchmark_data.csv")

# --- roofline hardware model ------------------------------------------------
PEAK = 102.4              # peak compute (GFLOP/s)
BW = 31.5                 # PCIe4 x16 link bandwidth (GB/s) — the roofline roof

# --- workload constants -----------------------------------------------------
SW_OPS, HW_OPS = 9, 62    # software FLOP/elem ; hardware OP/elem (incl. comparators)
SW_BYTES, HW_BYTES = 16, 8  # in+out bytes/elem: fp64 vs fp32
PEAK_ELEM = PEAK / SW_OPS  # peak compute expressed in elements/s = 11.38 G elem/s


# Measured configs (CSV row name, short lane label) by datapath.
DIRECT = [("x1", "x1_direct_stream"), ("x8", "x8_direct_stream"),
          ("x16", "x16_direct_stream"), ("x32", "x32_direct_stream")]
DMA = [("x1", "x1_dma_serial"), ("x8", "x8_wide_dma_serial"),
       ("x16", "x16_wide_dma_serial"), ("x32", "x32_wide_dma_serial")]


def throughputs():
    """All configs -> throughput in M elem/s, from the CSV."""
    with open(CSV) as f:
        return {r["config"]: float(r["throughput_Melem_s"]) for r in csv.DictReader(f)}


def draw_roofs(ax, peak, peak_text, ylim):
    ai = np.logspace(-2, 3, 500)
    ridge = peak / BW
    ax.plot(ai, np.minimum(BW * ai, peak), "r-", lw=2, zorder=1)
    ax.axvline(ridge, color="r", ls=":", alpha=0.5)
    ax.text(ridge * 1.3, peak * 1.15, peak_text, color="r", fontsize=8)
    ax.text(0.012, 0.012 * BW * 1.4, f"bandwidth {BW} GB/s",
            color="r", fontsize=8, rotation=40)
    ax.text(ridge * 1.08, peak * 0.55, f"ridge AI = {ridge:.3g}", color="r", fontsize=8)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlim(0.01, 1e3); ax.set_ylim(*ylim)
    ax.grid(True, which="both", alpha=0.3)


def save(fig, path):
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)
    print("wrote", os.path.relpath(path, ROOT))


def roofline(path, peak, peak_text, points, ai_label, perf_label, title, ylim):
    fig, ax = plt.subplots(figsize=(8, 6))
    draw_roofs(ax, peak, peak_text, ylim)
    for x, y, lab, c in points:
        ax.plot(x, y, "o", ms=9, color=c, zorder=3)
        ax.annotate(f"{lab}\n({x:.3g}, {y:.3g})", (x, y),
                    textcoords="offset points", xytext=(10, -4), fontsize=9, color=c)
    ax.set_xlabel(ai_label); ax.set_ylabel(perf_label); ax.set_title(title)
    save(fig, path)


def plot_swonly(t):
    """Software baseline only — the report §II roofline-analysis figure, matching
    the narrative (kernel is memory-bound, far below the roof)."""
    sw = t["software_baseline_per_forward"]
    roofline(
        os.path.join(ROOT, "report", "roofline_plot.png"),
        PEAK, f"peak compute {PEAK} GFLOP/s",
        [(SW_OPS / SW_BYTES, sw * SW_OPS / 1e3, "Software baseline (fp64)", "tab:purple")],
        "Arithmetic Intensity (FLOP/B)", "Performance (GFLOP/s)",
        "Roofline — software baseline (memory-bound, far below the roof)", (0.05, 1e3))


def plot_flop(t):
    sw, x8 = t["software_baseline_per_forward"], t["x8_direct_stream"]
    roofline(
        os.path.join(ROOT, "bench", "roofline_flop.png"),
        PEAK, f"peak compute {PEAK} GFLOP/s",
        [(SW_OPS / SW_BYTES, sw * SW_OPS / 1e3, "Software baseline (fp64)", "tab:purple"),
         (SW_OPS / HW_BYTES, x8 * SW_OPS / 1e3, "GELU x8 (M4, fp32)", "tab:blue")],
        "Arithmetic Intensity (FLOP/B)", "Performance (GFLOP/s)",
        "Roofline — floating-point view (9 FLOP/elem useful work)", (0.05, 1e3))


def plot_op(t):
    sw, x8 = t["software_baseline_per_forward"], t["x8_direct_stream"]
    roofline(
        os.path.join(ROOT, "bench", "roofline_final.png"),
        PEAK, f"peak compute {PEAK} GFLOP/s",
        [(SW_OPS / SW_BYTES, sw * SW_OPS / 1e3, "Software baseline", "tab:purple"),
         (HW_OPS / HW_BYTES, x8 * HW_OPS / 1e3, "GELU x8 (M4 accelerator)", "tab:blue")],
        "Arithmetic Intensity (OP/B)", "Performance (G OP/s)",
        "Roofline — integer-op view (62 ops/elem, incl. PWL comparators)", (0.05, 1e3))


def plot_elem(t):
    sw, x8 = t["software_baseline_per_forward"], t["x8_direct_stream"]
    roofline(
        os.path.join(ROOT, "bench", "roofline_final_elem.png"),
        PEAK_ELEM, f"peak compute {PEAK_ELEM:.2f} G elem/s",
        [(1 / SW_BYTES, sw / 1e3, "Software baseline (fp64)", "tab:purple"),
         (1 / HW_BYTES, x8 / 1e3, "GELU x8 (M4, fp32)", "tab:blue")],
        "Arithmetic Intensity (elem/B)", "Performance (G elem/s)",
        "Roofline — element-wise view (elements moved per byte)", (0.005, 1e2))


# All-configs views: each maps a throughput (M elem/s) to a roofline (AI, perf).
# Every HW config shares the same AI, so the points form a vertical scaling stack.
ALLVIEWS = {
    "allpts": dict(
        path=("bench", "roofline_all.png"), peak=PEAK,
        peak_text=f"peak compute {PEAK} GFLOP/s", ylim=(0.05, 1e3),
        sw_xy=lambda s: (SW_OPS / SW_BYTES, s * SW_OPS / 1e3),
        hw_xy=lambda thr: (HW_OPS / HW_BYTES, thr * HW_OPS / 1e3),
        ai_label="Arithmetic Intensity (OP/B)", perf_label="Performance (G OP/s)",
        title=f"Roofline — all measured configs (62 ops/elem; AI={HW_OPS/HW_BYTES:.3g} for all HW)"),
    "allelem": dict(
        path=("bench", "roofline_all_elem.png"), peak=PEAK_ELEM,
        peak_text=f"peak compute {PEAK_ELEM:.2f} G elem/s", ylim=(0.005, 1e2),
        sw_xy=lambda s: (1 / SW_BYTES, s / 1e3),
        hw_xy=lambda thr: (1 / HW_BYTES, thr / 1e3),
        ai_label="Arithmetic Intensity (elem/B)", perf_label="Performance (G elem/s)",
        title=f"Roofline — all measured configs, element-wise (AI={1/HW_BYTES:.3g} for all HW)"),
}


def plot_all(t, v):
    """Every measured config on one roofline. Parallelism scales straight up at
    the constant HW arithmetic intensity, so the points form a vertical stack."""
    from matplotlib.lines import Line2D
    fig, ax = plt.subplots(figsize=(8, 6))
    draw_roofs(ax, v["peak"], v["peak_text"], v["ylim"])

    sx, sy = v["sw_xy"](t["software_baseline_per_forward"])
    ax.plot(sx, sy, "o", ms=9, color="tab:purple", zorder=3)
    ax.annotate("software baseline", (sx, sy), textcoords="offset points",
                xytext=(10, -4), fontsize=8, color="tab:purple")

    # direct stream (blue circles, labels left) and wide DMA (orange squares, labels right)
    for lane, cfg in DIRECT:
        x, y = v["hw_xy"](t[cfg])
        ax.plot(x, y, "o", ms=8, color="tab:blue", zorder=4)
        ax.annotate(lane, (x, y), textcoords="offset points", xytext=(-11, -3),
                    ha="right", fontsize=8, color="tab:blue")
    for lane, cfg in DMA:
        x, y = v["hw_xy"](t[cfg])
        ax.plot(x, y, "s", ms=8, color="tab:orange", zorder=3)
        ax.annotate(lane, (x, y), textcoords="offset points", xytext=(11, -3),
                    ha="left", fontsize=8, color="tab:orange")

    ax.legend(handles=[
        Line2D([], [], marker="o", color="tab:blue", ls="", label="direct AXI-Stream"),
        Line2D([], [], marker="s", color="tab:orange", ls="", label="wide DMA (serial)"),
        Line2D([], [], marker="o", color="tab:purple", ls="", label="software baseline"),
    ], loc="lower right", fontsize=8)
    ax.set_xlabel(v["ai_label"]); ax.set_ylabel(v["perf_label"]); ax.set_title(v["title"])
    save(fig, os.path.join(ROOT, *v["path"]))


PLOTS = {
    "swonly": plot_swonly, "flop": plot_flop, "op": plot_op, "elem": plot_elem,
    "allpts": lambda t: plot_all(t, ALLVIEWS["allpts"]),
    "allelem": lambda t: plot_all(t, ALLVIEWS["allelem"]),
}


def main(argv):
    sel = [a for a in argv if a != "all"]
    if not sel or "all" in argv:
        sel = list(PLOTS)
    unknown = [a for a in sel if a not in PLOTS]
    if unknown:
        raise SystemExit(f"unknown plot(s): {unknown}; choose from {list(PLOTS)} or 'all'")
    t = throughputs()
    for name in sel:
        PLOTS[name](t)


if __name__ == "__main__":
    main(sys.argv[1:])
