Core Kernel Hierarchy of AI Operations: Top Level: Core Computational 
Kernels $\rightarrow$ 

1. Matrix Multiplication (GEMM): The most 
fundamental operation for deep learning. Sub-components: 
2. Convolutions (
(Conv): Special case of GEMM for spatial data. Sub-components: 
3. Element-
Element-wise Operations (Activation, etc.): Vectorized operations. 
4. Reductions (Pooling, Summation): Aggregating information over dimensions. $
$\rightarrow$ Supporting Elements & Optimizations: (These elements are 
used by the core kernels to function efficiently) $\rightarrow$  
    A. Activation Functions: Non-linear mappings. Types: ReLU (max(0, x)), 
Sigmoid ($\frac{1}{1+e^{-x}}$), Tanh ($\frac{e^x-e^{-x}}{e^x+e^{-x}}$), 
GELU. (Mathematical Implementations) $\rightarrow$   
    B. Quantization Schemes:
    Schemes: Reducing bit precision for efficiency. Types: Post-Training 
    Quantization (PTQ), Quantization-Aware Training (QAT). Formats: INT8, INT4.
INT4. $\rightarrow$   
    C. Data Type Support: Handling various numerical 
precision needs. Types: FP32, FP16, BFloat16, INT8. $\rightarrow$   
    D. Memory Hierarchy Management: Optimizing data movement. Concepts: Tiling, 
Block Decomposition. $\rightarrow$   
    E. Arithmetic Units: Specialized hardware acceleration. Examples: specialized ALUs for matrix 
multiplication.

