# Baseline Benchmark

## Platform Configuration

| Parameter | Value |
|-----------|-------|
| Platform | i5-8365U CPU @ 1.60GHz |
| Batch Size | 8 |
| Sequence Length | 64 |
| D_ff | 256 |

CLI Command: `train.py --steps 500 --config small --generate --prompt "Alice"` 
> **Note:** The `--generate` flag increases forward pass (inference) count, and therefore total GELU call count.

---

## GELU Performance Results

| Metric | Value |
|--------|-------|
| Execution Time | 10.202 s |
| Throughput | 185 MFLOPs/s |
| Memory Usage | 5,380.797 MiB |
| Arithmetic Intensity | 0.335 FLOPs / byte |