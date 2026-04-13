# Partition Rationale


## a. Target Kernel for hardware

Based on the results of the ai alagorithm profiling in project_profiling.md, of small, medium, and large profile, targeting the **GELU kernel** will yeild the greatest impact. While the **gelu_grad** kernel has the overall highest total time contribution **gelu** is also used for inference. **gelu_grad** only contributes to backwards propagation, i.e. training while **gelu**, the activation function will contribute to both training and inference time. If possible the HDL will be expanded to cover both due to similarities, but this would be a stretch goal. Increasing the configuration from small to large greatly impacts mha which makes MHA a strong candidate for optimization as well, however the gelu kernel still yield the greatest footprint on our profiling. Another thing to note is AI algorithm runs inefficiently on Python due to the overhead and the tanh function is part of the numpy library, if the kernels are ran on a C++ library this would give us a better picture of the current actual bottonecks in modern local or cloud ai models. Another thing to note is there are 3 kernels in MHA each yeilding a fraction of observed MHA contribution. Traffic can be reduced by joining ff_forward and GELU to keep the memory access in one place. The roofline analysis shows the kernel is memory bound, so joining ff_forward and Gelu is a good method to reduce memory transfers. 

Gemini database notes:  
+ MHA is the core component of almost every transformer architecture (BERT, GPT, ViT), making it an essential, defining feature of modern deep learning.
+ GELU is a popular activation function (used in BERT and GPT-2), but it is one of several choices, often substituted with ReLU or Swish depending on the specific model architecture

## b. Software kernels

The software will continue to handle backwards and forward kernels of ff, mha, and normalization (softmax). This was based on runs with small, medium, large configurations. However MHA kernel optimization is still a strong candidate and would be optimized if time permits. Though due to the cost of data transfer to hardware, the next closest function to gelu is the feed forward layer, then MHA considering data locality. Effective optimization prioritization starting with the activation kernel would be `GELU` > Kernel 4: `Feed-Forward`  > Kernel 1-3: `MHA`. 

## c. interface bandwidth
To prevent interface bound at target throughput, the floor memory thoughput was calculated to be 202.90 MiB/s (theoretical) to match SW profile (see ai_calculation). This does not include any computation time in the accelerator. PCIe or AXI stream is recomended to achive a more likely minimum of ~500MiB/s and allow for computation time at the accelerator. PCIe is chosen as the interface of choice.

## d. Kernel bounds
Based on the roofline analysis the kernel is **memory-bound**. Moving the gelu values to external hardware imposes a flat dataflow tax on the 2N inputs that the external hardware operates on, however this is generally less than other kernels because weights are not transferedk only input and output. As mentioned previously, dataflow can be mediated by including the entire ff_forward kernel in the accelerator and keep the data in the same place. This would be one of the stretch goals after implementation of GELU. Normally **compute-bound** kernels should be selected, however while gelu kernel is memory bound in theory, it is very poorly optimized currently due to (asumption) the Python function calls. There is alot of room for optimization since the profiled result shows gelu being way below the memory-bound roofline. 


## Resource AI analysis of functions: Transformer Forward Path Kernel Breakdown

### Kernel 1: Attention Projections (Q, K, V, O)
* **Math (`mha_forward`):** $Q = XW_q + b_q, K = XW_k + b_k, V = XW_v + b_v, Out = Context \cdot W_o + b_o$
* **Why/Hardware Impact:** These are high-density GEMM (General Matrix Multiply) operations that transform the input into the query, key, and value spaces. In hardware, these are typically throughput-bound. Because $d$ is often large (e.g., 512 or 768), these operations represent the primary consumers of Multiply-Accumulate (MAC) cycles in a systolic array or TPU-like architecture.

### Kernel 2: Attention Scores (QKᵀ)
* **Math (`mha_forward`):** $Scores = \text{Softmax}(\frac{QK^T}{\sqrt{d_h}})$
* **Why/Hardware Impact:** This kernel is mathematically unique because its complexity is quadratic ($O(T^2)$) relative to the sequence length. In hardware, this is frequently memory-bandwidth bound rather than compute-bound because the intermediate score matrix can grow significantly larger than the hidden dimension $d$. It also requires specialized logic for causal masking to prevent the model from "looking ahead."

### Kernel 3: Attention Weighted Sum (AV)
* **Math (`mha_forward`):** $Context = \text{AttentionWeights} \cdot V$
* **Why/Hardware Impact:** Like Kernel 2, this scales quadratically with sequence length. Architecturally, this functions as a "Gather" operation. To avoid stalling the compute units, hardware must support efficient non-sequential data movement, pulling information from across the entire sequence based on the dynamically calculated attention weights.

### Kernel 4: Feed-Forward (Linear 1 & 2)
* **Math (`ff_forward`):** $H = XW_1 + b_1$ and $Out = H_{act}W_2 + b_2$
* **Why/Hardware Impact:** These matmuls typically involve the highest parameter counts in the model, as the hidden dimension ($d_{ff}$) is often $4 \times$ the model dimension ($d$). These kernels are the primary storage for the model's learned weights. On an FPGA or ASIC, the challenge here is minimizing the energy cost of moving these large weight matrices from off-chip memory (DRAM) to on-chip SRAM.

### Kernel 5: GELU Activation
* **Math (`gelu`):** $0.5x(1 + \tanh(\sqrt{2/\pi}(x + 0.044715x^3)))$
* **Why/Hardware Impact:** This is an element-wise activation function. While the FLOP count is low compared to GEMMs, the math is "expensive" due to transcendental operations ($\tanh$ and square root). High-performance hardware often implements this using a piecewise linear approximation or a Look-Up Table (LUT) to trade a small amount of precision for a massive gain in area and power efficiency.

Implementation Context

In your transformer.py script, these kernels are distributed as follows:  
+ Kernels 1, 2, and 3 are all contained within `mha_forward`. This function manages the split-head logic and the causal mask before merging the results back into the model dimension.
+ Kernel 4 is the core of `ff_forward`, which handles the two-stage projection.
+ Kernel 5 is defined as the standalone `gelu` function, which is called mid-way through `ff_forward`