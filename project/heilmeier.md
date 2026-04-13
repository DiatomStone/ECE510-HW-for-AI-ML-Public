1. What are you trying to do? Articulate your objectives using absolutely no jargon.
> Target GELU kernel of sample transformer algorithm to accelerate with HDL.  Roofline analysis reveal GELU is memory bound. The implementation is staged by priority one kernel must be functional before the next. PCIe → DMA → GELU → ff_forward → gelu_grad.
 
2. How is it done today, and what are the limits of current practice?
> Three general aproach: algorithmic shortcuts, compiler-level "fusion," and hardware-specific instructions.
>- algorithmic shortcut: tanh aproximation is used in current kernel but 
Sigmoid Approximation (SiLU-like) trades small precision loss for improved execution time.
>- compiler-level "fusion": noted as most important optimization.
combines multiple load store steps, loads x once and store GELU result once. 
>- hardware (SIMD): leverage intel AVX intrinsics or SFU in NVidia GPU to do math quickly.
>- The current method is SW implementation with python which results in a large function call overhead. Profiling data shows a large slowdown due to Gelu, which accounts for 21.4%, 25.4%, and 19.8% of execution time in small, medium, large configurations respectively. The Kernel performance was shown to be well below the memory-bound roofline at an observed 114 MFLOPs/s.

3. What is new in your approach and why do you think it will be successful?
> + My approach be similar to NVIDIA's apprach to build specialized hardware to target GELU function.  
 Memory access should be minimal, not involve python call overheads, and would not involve long `CUDA_INIT()` time for all of nvidia's other capabilities. PCIe is  selected as the hardware interface, with Memory bandwith requirement of no lower than 500 Mb/s (202.90 MiB/s minimal dataflow time to match sw).
 > + Nvidia's GPU approach is more generalized for most functions while the chiplet aims to be a 7 stage pipeline for GELU with 16 parallel lanes.
 > + If posible, implementation of feed forward and gelu together would reduce RAM access. 
 
4. Who cares? If you are successful, what difference will it make?
5. What are the risks?
6. How much will it cost?
7. How long will it take?
8. What are the mid-term and final “exams” to check for success? 


