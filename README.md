Name: Nhat Nguyen
Course: ECE 510 Sprint 2026
Project topic candidate: GELU kernel

## Overview
module: gelu @ [gelu.sv](project/hdl/gelu.sv)   
Interface: PCIe   
Precision: 32 bit   
Justification: from fp64 to fp32 then passing to the gelu kernel results in less bandwidth required for data transfer and increased AI. This was previously discussed in greater detail @ [interface_selection.md](project/m1/interface_selection.md)

## Project/cocotb_toolchain 
This is an atempt of understanding SW/HW pipeline. AXIS file was successfuly piped from cocotb to a simple accelerator and piped back. full test of pcie/dma → memory via axis → accelerator via axis and back is tested but not yet functional. 

### Local LLM survey: 
The point of the Local LLM survey is to better understand the
landscape and use of AI, and become embeded in AI terminology.

# GELU Hardware Accelerator — ECE 410/510

A custom hardware accelerator for the **GELU activation kernel**, which M1 profiling
identified as 21.4% of the runtime of a small GPT-2-style transformer. The design
offloads every FFN GELU of the transformer to hardware: FP32 in → an internal
Q16.16 piecewise-linear (PWL) approximation → FP32 out, as a pipelined **12-cycle,
1-result/cycle/lane** datapath. It is parameterized for SIMD width (`NUM_LANES`);
the final hardened design is the **8-lane streaming** build (`gelu_top`), placed-and-
routed in OpenLane 2 / sky130A at a **22 ns (45.45 MHz)** clock with timing met at
every corner. Measured in cycle-accurate co-simulation against the all-software
model, it reaches **~16× end-to-end speedup** (8 lanes) at **~1700× lower energy**,
with a max GELU error of 0.026 (well inside the 0.05 contract).

## Milestone 4 — final deliverable

- **M4 file catalog / index:** [`project/m4/README.md`](project/m4/README.md)
- **Design justification report (PDF):** [`project/m4/report/design_justification.pdf`](project/m4/report/design_justification.pdf)
- **Benchmark + speedup vs software:** [`project/m4/bench/benchmark.md`](project/m4/bench/benchmark.md)
- **Synthesis results (sky130A, x8):** [`project/m4/synth/`](project/m4/synth/)

Earlier milestones (M1–M3 profiling, precision, and verification work) are under
`project/m1/`–`project/m3/`; M4 supersedes them as the complete, synthesized,
benchmarked package.
