Name: Nhat Nguyen
Course: ECE 510 Sprint 2026
Project topic candidate: GELU kernel

## Overview
module: gelu @ [gelu.sv](project/hdl/gelu.sv)   
Interface: PCIe   
Precision: 32 bit   
Justification: from fp64 to fp32 then passing to the gelu kernel results in less bandwidth required for data transfer and increased AI. This was previously discussed in greater detail @ [interface_selection.md](project/m1/interface_selection.md)

## Module function: 
This module currently performs gelu in a 5 stage pipeline the input values are all used in the first pipeline slot therefore at every clock we can process a new value. This is meant be instantiated at least 16 times to process 16 gelu operations in parallel. A high level breakdown of this gelu.sv is found in [GELU_calculations.md](project/GELU_calculations.md). 




### Local LLM survey: 
The point of the Local LLM survey is to better understand the
landscape and use of AI, and become embeded in AI terminology.