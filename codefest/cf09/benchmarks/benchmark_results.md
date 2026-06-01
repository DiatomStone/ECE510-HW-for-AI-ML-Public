# Baseline 
parameters train.py --config small --steps 500
|Baseline|Metric|
|--|--|
|Total execution time |44.085s|
|Gelu execution time| 9604 ms|
|Throughput| 13.647 K elem/s| 
|Throughput| 122.8 K flops/s| 
|Memory-profiler result gelu |294.477 Mib *| 
|Theoretical Input memory | 2^17 * 

- memory profile -1713.062 Mib - 2000.539 Mib = 294.477 MiB (1000 calls) 0.294477 Mib per call 
- total floating operation 9 per gelu
- shape = 2^17 = 64 * 8 * 256 = 2^6 * 2^3 * 2^8 = sequence * batch * dff 
- throughput = 2^17 / 9.604 s = 13647.65 elements/s
- throughput = 13647.65 elements/s * 9 = 122.8 Kflops/s
- note software does math in FLOPS but our accelerator uses int operations, so this is simplified to OPS
- Bytes = 2^17 * 2^3 (fp64) = 1 MB
# Accelerated kernel
|Accelerated kernel |Metric|
|--|--|
|Gelu execution time| 6.062 ms|
|Measured Throughput| 45.45 M elem/s| 
|Throughput| 2.8179 G Ops/s|          
|Memory | streaming*| 
|Measured AXI bandwidth | 363.3 MB/s|
|Total power | 30.22 mW |
|Total chip area|  90,470.52 µm²|
|speedup | 1584.3x | 

**Memory buffers exist and has passed simulation, but has not yet been synthesized with openlane due to specific openmemory instantiations (not simple brams) requirements. Since those modules are not yet synthesized. They are ommited from this section.
** open  

## Throughput calculation
62 per gelu pass in hardware (cf09 cman)
throughput = 45.45 M elem/s * 62 = 2.8179 B Ops/s



# simulation result (tb_top_inloop.py)
```
                                                         === Full-Model In-Loop GELU Co-Sim — Timing & Metrics ===
5772492.00ns INFO     cocotb.gelu_top                      Model              : M1 transformer, 2 layers, B=8 T=64 d_ff=256 (seed=42)
5772492.00ns INFO     cocotb.gelu_top                      GELU offloads      : 2 (one per layer FFN)
5772492.00ns INFO     cocotb.gelu_top                      Elements streamed  : 262144  in 16 AXI frames
5772492.00ns INFO     cocotb.gelu_top                      Clock (synth)      : 22 ns  (45.45 MHz)
5772492.00ns INFO     cocotb.gelu_top                      --- MEASURED (cycle-accurate Icarus) ---
5772492.00ns INFO     cocotb.gelu_top                      HW streaming time  : 5772096 ns (~262368 cycles)
5772492.00ns INFO     cocotb.gelu_top                      Throughput         : 45.42 M elem/s  (1.001 cycles/elem)
5772492.00ns INFO     cocotb.gelu_top                      AXI bandwidth/dir  : 181.7 MB/s (in, and out)
5772492.00ns INFO     cocotb.gelu_top                      AXI bandwidth total: 363.3 MB/s (in+out)
5772492.00ns INFO     cocotb.gelu_top                      --- PROJECTED PEAK (synthesis × ops/cycle) ---
5772492.00ns INFO     cocotb.gelu_top                      Peak throughput    : 45.45 M elem/s  (1 result/cycle @ 22 ns)
5772492.00ns INFO     cocotb.gelu_top                      Peak int-arith     : 772.7 M op/s  (17 ops/elem)
5772492.00ns INFO     cocotb.gelu_top                      --- HOST-SIDE CONVERSION (informational, not kernel time) ---
5772492.00ns INFO     cocotb.gelu_top                      fp64<->fp32 casts  : 289.5 us total (host, both directions)
5772492.00ns INFO     cocotb.gelu_top                      --- KERNEL ACCURACY (per-element, all layers) ---
5772492.00ns INFO     cocotb.gelu_top                      GELU max error     : 0.026311
5772492.00ns INFO     cocotb.gelu_top                      GELU failures      : 0 / 262144  (threshold 0.05)
5772492.00ns INFO     cocotb.gelu_top                      --- LOOP CLOSURE: final logits vs all-software forward() ---
5772492.00ns INFO     cocotb.gelu_top                      Logits avg / max   : 0.015396 / 0.104763
5772492.00ns INFO     cocotb.gelu_top                      Next-token argmax  : 503/512 positions match software
5772492.00ns INFO     cocotb.gelu_top                    =========================================================
PASS
5772492.00ns INFO     cocotb.gelu_top                    PASS
5772492.00ns INFO     cocotb.regression                  tb_top_inloop.test_gelu_top_inloop passed
5772492.00ns INFO     cocotb.regression                  ********************************************************************************************
                                                         ** TEST                                STATUS  SIM TIME (ns)  REAL TIME (s)  RATIO (ns/s) **
                                                         ********************************************************************************************
                                                         ** tb_top_inloop.test_gelu_top_inloop   PASS     5772492.00          43.42     132954.15  **
                                                         ********************************************************************************************
                                                         ** TESTS=1 PASS=1 FAIL=0 SKIP=0                  5772492.00          43.42     132949.66  **
                                                         ********************************************************************************************
FST info: dumpfile sim_build/gelu_top.fst opened for output.
```

tb_top_inloop.py — scope: A full-model, hardware-in-the-loop cocotb co-simulation. It runs the M1 transformer's forward pass using transformer.py's real functions and weights, and offloads every GELU activation (both layers, 262,144 elements total) to the actual gelu_top RTL over the AXI-Stream/AXI-Lite interface — casting fp64→fp32 in, fp32→fp64 out, streamed in ≤16,384-element frames. Hardware results propagate forward, closing the loop. It verifies per-element GELU accuracy against software and checks final logits, then reports measured throughput, cycles/element, and AXI bandwidth at the synthesized 22 ns clock.  

MEASURED (cycle-accurate Icarus)  
HW streaming time  : 5772096 ns  
fp64<->fp32 casts  : 289.5 us total (host, both directions)  

total accelerated kernel time = 5772.096 us + 289.5 us = 6061.596 us = 6.062 ms

`Speedup = 9604 ms/6.062 ms = 1584.3x speedup` 

The total AXI bandwith here is the limiting factor since we are only doing 1 pipeline. (AXI bandwidth total: 363.3 MB/s (in+out))
Claude projection of PCIe inclusion : 

**Per-pipeline demand (measured):** 1 FP32/cycle @ 45.45 MHz = 181.8 MB/s per
direction (in and out), 363.6 MB/s aggregate; 45.45 M GELU/s.

**PCIe Gen4 DMA — projected scaling** (16 GT/s/lane, 128b/130b, per direction,
full-duplex; throughput = pipelines × 45.45 M GELU/s):

| Link | Theoretical BW/dir | Pipelines it can feed (÷181.8 MB/s) | Projected throughput (full fill) |
|------|--------------------|-------------------------------------|----------------------------------|
| x1   | 1.97 GB/s          | ~10                                 | ~0.49 G GELU/s                   |
| x4   | 7.88 GB/s          | ~43                                 | ~1.97 G GELU/s                   |
| x8   | 15.75 GB/s         | ~86                                 | ~3.9 G GELU/s                    |
| x16  | 31.5 GB/s          | ~173                                | ~7.9 G GELU/s                    |

Derate ~10% for TLP/header overhead (MPS-dependent) for a practical figure.
All values projected from link theory × synthesized 45.45 MHz throughput, not measured.