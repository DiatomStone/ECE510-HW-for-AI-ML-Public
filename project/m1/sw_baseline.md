# Baseline Benchmark

## Platform Configuration

| Parameter | Value |
|-----------|-------|
| OS | linux 6.17.0=14-generic|
| Distribution| Ubuntu 24.04.1 |
| Python version | 3.12.3 |
| CPU | i5-8365U CPU @ 1.60GHz|
| Memory | 16 GB dual channel 2400 MHz|
|Peak Performance| 102.4 GFLOPs/s|
|Peak Bandwidth| 38.4 GB/s|
| Batch Size | 8 |
| Sequence Length | 64 |
| D_ff | 256 |

GFLOPs/s retrieved from APP Metrics for Intel® Microprocessors

CLI Command: `train.py --steps 500 --config small --generate --prompt "Alice"` 
> **Note:** The `--generate` flag increases forward pass (inference) count, and therefore total GELU call count.

---

## GELU Performance Profiling
|Run|Gelu time|Gelu_grad time|Total |Gelu %|
|---|---|---|---|---|
|1 small|9.652|10.461|44.133|21.9%|
|2 small|9.668|10.49|44.516|21.7%|
|3 small|10.099|10.941|46.897|21.5%|
|4 small|10.244|11.103|46.999|21.8%|
|5 small|10.615|11.44|49.274|21.5%|
|6 small|10.603|11.496|49.478|21.4%|
|7 small|10.428|11.34|48.691|21.4%|
|8 small|10.234|11.086|47.673|21.5%|
|9 small|11.152|12.027|59.072|18.9%|
|10 small|10.891|11.81|54.4|20.0%|
|11 small|10.845|11.691|51.459|21.1%|
|12 small|9.211|10.108|44.059|20.9%|
|---|---|---|---|---|
|1 medium|168.748|190.089|673.519|25.1%|
|2 medium|166.645|188.163|656.446|25.4%|
|3 medium|168.759|190.29|662.633|25.5%|
|---|---|---|---|---|
|1 large|472.079|552.88|2388.187|19.8%|

## GELU Performance Results (small profile)

| Metric | Value |
|--------|-------|
| Execution Time (median) | 10.336 sec |
| total runtime (median) | 48.182 sec |
| percentage (median) | 21.4 %|
| Memory usage | 2172.969 MiB | 
| Performance Throughput | 114 MFLOPs/s |
| Memory Usage | 2172.969 MiB |
| Arithmetic Intensity | 0.335 FLOPs / byte |