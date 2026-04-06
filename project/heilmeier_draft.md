1. What are you trying to do? Articulate your objectives using absolutely no jargon.
> Target GELU kernel of sample transformer algorithm to optimize with HDL.  
GELU_grad is also promising if the focus is training, but GELU is used in both inference and training.  
Analysis of arithmatic intensity and roofline plot suggests GELU kernel is memory bound.  
Gemini sugests issue is due to python function call and allocation overhead. 

2. How is it done today, and what are the limits of current practice?
> Three general aproach: algorithmic shortcuts, compiler-level "fusion," and hardware-specific instructions.
>- algorithmic shortcut: tanh aproximation is used in current kernel but 
Sigmoid Approximation (SiLU-like) trades small precision loss for improved execution time.
>- compiler-level "fusion": noted as most important optimization.
combines multiple load store steps, loads x once and store GELU result once. 
>- hardware (SIMD): leverage intel AVX intrinsics or SFU in NVidia GPU to do math quickly.
3. What is new in your approach and why do you think it will be successful?
> My approach be similar to NVIDIA's apprach to build specialized hardware to target GELU function.  
 Memory access should be minimal, not involve python call overheads,  
 and would not involve long `CUDA_INIT()` time for all of nvidia's other capabilities. 
 PCIe is tentatively selected as the hardware interface, with Memory bandwith requirement of no lower than 500 Mb/s.
 (more details in transformer_analysis.md)
 
4. Who cares? If you are successful, what difference will it make?
5. What are the risks?
6. How much will it cost?
7. How long will it take?
8. What are the mid-term and final “exams” to check for success? 


