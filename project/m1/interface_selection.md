# 1. Interface Selection and Host platform
Since Calculation thus far has been on a local machine, a local machine Host on a consumer computer system is a point of interest to run local LLM. This allows for USB or PCIe interfaces. PCIe interface is be chosen.

# 2. Bandwidth requiremnt of kernel

Current estimation: 
+ Average gelu time per call across 12 runs (1000 calls each): 0.0103 s
+ Total bytes per gelu call 2097152 Bytes 
+ Current SW bandwidth requirement: Bytes/time = 2097152 Bytes / 0.0103 s = 0.2036 GB/s 
+ Utilization bandwidth (RAM) at SW speed = 0.2036 GB/s / 38.4 GB/s = 5.3%

PCIe 4: max speed is 32 GB/s, this would be the new roofline slope

Consideration:
fp64 operations is not ideal for gelu or hardware, some simplification may be performed first to reduce fp64 to fp32 or fp16. This would also greatly improve calculation speed and pressure on the bus. fp64 also cost more resource to perfrom the operations.

Target estimation: 
current design (GELI_calculations.md) calls for a pipeline (5 stage simple flop + 1 complex flop) that process 1 64fp point, with 16x parallel (to be determined) pipelines. Frequency in the accelerator is not fixed so we can clock upto the longest stage in the pipeline. 

### Asuming full fp64
+ Attempt 1:
**total input shape**: B × T × d × 8 bytes = 8 × 64 × 256 × 8 = 1048576 Bytes
**input and output per pipeline stage**:  16 × 8 bytes × 2 =  256 Bytes / cycle
Accelerator @ 512 Mhz: 256 Bytes/cycle * 512 Mhz (Mcycles/second) = 128 GB/s bandwidth (too fast)

+ Attempt 2: 
Accelerator @ 128 Mhz: 256 Bytes / cycle * 128 Mhz (Mcycles/second) = 32 GB/s bandwidth consumption and return
Utilization : 32 GB/s  / 32 GB/s =  100%  (this would likely break)

### Asuming fp32 pre-bus conversion
tax is a flat conversion step, but this allows for much cheeper hardware and less bandwidth consumption meaning higher clock and faster processing. 

Asume 4 average cycle per stage.  
**input and output per pipeline stage**:  16 × 4 bytes × 2 /4  =  32 Bytes / cycle

+ Atempt 3:  
Accelerator @ 128 Mhz: 32 Bytes/cycle * 128 Mhz = 8 GB/s
Utilization: 4 GB/s / 32 GB/s = 12.5%
Processing time estimate: total bytes (per gelu operation * gelu calls)/(consumption * Clock) = 1048576 * 1000 / (32 * 128 MHz) = 0.256 seconds
max speedup = 10.336/0.256 = 40.375x 
This may be more feasible since it would take 1-4 cycles to do a simple FLOP at 128 MHz. Cost can be reduced by using fp16, and PCIe bus utilization can be increased with parallelization. 

# 3. Interface rated bandwidth vs required bandwidth
The design proposed in attempt 3 does not fully saturate the PCIe bus, at 12.5% utiliy. This allows room for other system utility and overhead. The expected processing time is to be 0.256 seconds for the small gelu operation, with a max expected speed up of 40.375x. This does not take into consideration of the transfer time with dma and other transfer overhead or the flat fp64  to fp32 conversion tax, however we should still be under the Interface rated bandwidth limit of PCIe gen 4.