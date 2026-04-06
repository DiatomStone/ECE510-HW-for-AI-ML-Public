# Transformer Performance Analysis

## Overview

Based on **cProfile** runtime profiling. Most execution time is spent in `gelu` and `gelu_grad`.

### Call Hierarchy

| Pass | Functions Called |
|------|-----------------|
| **Forward** | `mha_forward`, `ff_forward`, `gelu` |
| **Backward** | `mha_backward`, `ff_backward`, `gelu_grad` |

- **Forward pass** — execution phase: calculates output and loss for a given input
- **Backward pass** — learning/correction phase: calculates direction and magnitude of parameter changes

Both passes repeat for every layer, with the number of layers (`n_layers`) set by CLI config: `small`, `medium`, or `large`.

---

## Bottleneck: GELU Activation

`gelu` is called in `ff_forward`; `gelu_grad` is called in `ff_backward`. The activation function appears to be the **primary bottleneck** and the main candidate for HDL-based optimization.

### What is GELU?

**GELU** (Gaussian Error Linear Unit) is the modern standard activation function for transformers. It smooths out the harsh corners of older functions like ReLU.

```
0.5 * x * (1.0 + tanh(sqrt(2.0 / π) * (x + 0.044715 * x³)))
```

---

## Memory Profile

| Metric | Value |
|--------|-------|
| Total cumulative allocation | 5,380.797 MiB |
| Total calls (incl. inference/generate) | 1,600 |
| Allocation per call | 3.36 MiB |

---

## FLOP Analysis

### Input Shape
```
Batch × Seq_len × D_ff = 8 × 64 × 256 = 131,072 elements
```

### Computation

| Metric | Calculation | Result |
|--------|-------------|--------|
| FLOPs per operation | 9 (including 1 complex `tanh`) | 9 FLOPs |
| FLOPs per call | 9 × 131,072 | 1,179,648 |
| Total FLOPs | 1,600 × 1,179,648 | **1.887 GFLOPs** |

### Arithmetic Intensity

| Metric | Value |
|--------|-------|
| Total memory | 5,380.797 MiB = 5,642,174,595 bytes |
| Total FLOPs | 1,887,436,800 |
| **Arithmetic Intensity** | **0.335 FLOPs / byte** |

> Low arithmetic intensity confirms GELU is **memory-bandwidth bound**, reinforcing it as the primary optimization target.

### Roofline plot by GEMINI
![Alt text](logs/roofline_gemini.png)

### Hardware interface
Model suggests a memory bound issue with Software overhead lowering the throughput FLOPs. Though peak system memory was never hit.  
The new throughput FLOPS would change after the putting GELU on hardware. At the minimum AXI_lite should be used.  
Axi stream or PCIe is a good candidate, A deeper inspection is required since if this is scaled up to a large configuration GELU might not be the biggest bottleneck.  
Tentatively PCIe is selected as the hardware interface to learn more about PCIe. currently ~10 seconds is required to transfer ~5.3 GB *AND* perform operations.  
So a minium of ~500 MB/s is needed.
