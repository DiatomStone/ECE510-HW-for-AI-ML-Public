
+ FP32 = 4 bytes
+ N = 32 = 2^5 
+ T = 8 = 2^3
1. Native triple loop
Each element of B is accessed N times, A is accessed N times per C element
+ across the full NxN output, the access would be:
    + A access = b access = c shape* row/col per c = N^2 x N = N^3 = (2^5)^3 = 2^15 = 32768 
    + memory load = A and B access = 2N^3 = 65536 floats 
    + memory write = N^2 (for the c matrix) =  (2^5)^2 = 1024 floats 
+ Traffic = (load + write) * byte = (2N^3 + N^2) * 4 = 8N^3 + 4N^2
    + Traffic = (65536 + 1024) * 4 = 266240 bytes = 260 KB

2. tiled 

+ In this method we do **Calculation per C tile** and throw out the required B and A loads after each C tile calculation
    + loads = tile size * num tiles
    + A loads = B loads= T^2 * N/T = NT = 2^5 * 2^3 = 2^8 = 256
    + per C tile = a load + B load = 2NT
    + memory loads = tiles * loads per c tile = (N/T)^2 * 2NT = 2N^3/T = 2(32)^3/8 = 8192 floats 
    + memory write = N^2 (for the c matrix) = 1024 floats 
+ Total dram traffic:  
    + Traffic = (load + write) * byte = (2N^3/T + N^2) *4 = 8 N^3/T + 4N^2
    + Traffic = (8192 + 1024) *4 = 36864 bytes = 36 KB

+ Following slides:  
    + each element of A and B is read from Dram once. Asuming cached a and B matrix (all values sent and held in VRAM and is **reused**)
    + A and B each loads the full matrix, N^2 per matrix, 2N^2 total
    + memory loads = 2N^2 = 2*32^2 = 2048 floats 
    + memory writes = N^2 = 1024 floats 
+ Total dram traffic: 
    + Traffic = (load + write) * byte = 3N^2 * 4 = 12N^2 
    + Traffic = 12(32)^2 = 12288 bytes = 12 KB

3. Compute Dram traffic to tiled DRAM traffic
+ Following traditional Tiled matrix multiplicaiton:
    + with write traffic naive VS tiled: (2N^3 + N^2) * 4 /(2N^3/T + N^2) *4 = (2N + 1) / (2N/T + 1)
    + no Write traffic: (2N + 1) / (2N/T + 1) = 2N / (2N/T) = T 
    + ratio = T:1
+ Following slides: 
    + naive vs fully reused (slides) (considering write traffic)= (8N^3 + 4N^2) / 12N^2 = (2N + 1)/3 = 2/3 N 
    + no write traffic (following slides): 2N^3 *4  / 2N^2 * 4 = N
    + ratio = N:1
+ The ratio of native to tiled traffic is N (32:1) if N is very large (neglectable write traffic) and A and B matrix is transfered once (cached and reused in VRAM). Justification: Native use N times more since B/A is accessed again N times for other C elements. 
+ The ratio of native to tiled traffic is T (8:1) if N is very large (neglectable write traffic) and we do traditional tiling (we cannot hold the entire A/B/C matricies in cache/VRAM), and only 1 tile of A/B/C is held at once. Justificiation: This makes sense if "Each tile element is reused T times for dot products within the tile" we expect the tiled GEMM to use up 1/T traffic of the naive GEMM. 

4. Execution time 
    + Bandwidth 320 GB/s (much faster than DRAM or PCIE, SOC config?) 
    + Compute 10 TFLOPS (comparable to panther lake i9/ RTX 2080)
    + Ridgeline point = 10K/320 = 31.25 FLOPs/B
    + FLOPS = 2 x N^2 x N  = 64K flops  
    + AI = FLOPS/Bytes
    + (AI < Ridgepoint ) ? Memory bound : Compute bound; 

    | Model | Formula | Bytes | AI (FLOPs/B)|  Bound | 
    |:-----|:-----:|:-----:|:-----:|:-----:| 
    | Traffic_naive | (2N^3 + N^2) * 4 | 260 KB |  0.2462 | Memory|
    | Traffic_tiled_trashing | (2N^3/T + N^2) *4 | 36 KB |  1.7778 | Memory | 
    | Traffic_tiled_resused | 3N^2 *4 |  12 KB |  5.333 | Memory|


    Time = Transfer + compute:   
    + Naive = 260 KB/320 GB/s + 64 KFLOPs/ 10 TFLOPS = 812.5 ns + 6.4 ns =  818.9 ns
    + tiled_trashing = 36K/320B + 6.4 ns = 112.5 ns +  6.4 ns = 118.9 ns
    + tiled_reused = 12K/320B + 6.4 ns = 37.5 ns + 6.4 ns = 43.9 ns