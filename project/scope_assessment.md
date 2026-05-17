# scope
- Project is continuing as expected, GELU works well. continue with scope
- ensure axi and parallelization works well together.
- parallelize to match bandwidth instead of 16x unless doing mac
    - possibly remove the 16x parallization alltoghether since we may not meet bandwidth.
- check pci DMA for openlane2 and how to integrate with code
- software/hardware integration is key point to focus on.
- expand and add mac kernel(weight stationary systolic) after hardware/software integration works
- mac + activation layout will end up looking like a tpu if possible. 
