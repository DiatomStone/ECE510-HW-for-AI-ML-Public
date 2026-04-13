### Dominant kernel 
The dominant kernel is GELU_grad and GELU, accounting for 23.3% and 21.4% of total runtime respectively. 
GELU is chosen as the primary target due to its application in inference dispite being the second larget contribution to runtime.


### FLOPs 
**GELU**: $0.5x(1 + \tanh(\sqrt{2/\pi}(x + 0.044715x^3)))$  
+ **count of float operations**: 6 mul + 2 add + 1 tanh = 9 FLOPS
+ **input shape**: N = B × T × d × = 8 × 64 × 256 = 131072 gelu operations
+ **total FLOPs**: FLOPs * input shape  = 9 * 131072  = 1179648 FLOPs

### Bytes transfered
+ No weights in GELU, so bytes transfered should be input + output= 2N 
+ **input shape bytes**: N × 8 bytes= B × T × d × 8 bytes = 8 × 64 × 256 × 8 = 1048576 Bytes 
+ **total Bytes transfered**: 2 × N × 8 = 2 × 1048576 = 2097152 Bytes 

### Arithmetic intensity
+ **Arithmetic intensity**: AI = FLOPs / Bytes =  9 × N/ (2 × N × 8)  = 9/16 = 0.5625 FLOPs/B

Based on the Arithmetic intensity this seems to be compute bound.

### Roofline calculations 
+ Peak HW Performance 102.4 GFLOPs/s
+ Peak HW Bandwidth 38.4 GB/s
+ **Ridge point**: peak FLOP/s ÷ peak bandwidth = 102.4 GFLOPs/s ÷ 38.4 GB/s = 2.667 FLOPs/B
+ SW profiled average gelu total time = 10.336 sec
+ **Profiled performance** = FLOPS/gelu * gelu calls / time = 1179648 * 1000 / 10.336  = 0.114 GFLOPs/s

## Floor Bandwidth estimateion
### profile based
+ SW profiled allocation for Gelu (average) = 2172.969 MiB
+ inputs must travel there and outputs back: 2N
+ Asumption is the allocated space is fully utilized.
+ Floor bandwidth based on profile = profiled allocation × 2 / profiled time = 2172.969 × 2 / 10.336 = 420.47 MiB/s
### Theoretical base
+ Floor bandwidth = Total bytes transfered per GELU * number of calls / profiled time = 2097152 *1000 / 10.336 = 202.90 MiB/s