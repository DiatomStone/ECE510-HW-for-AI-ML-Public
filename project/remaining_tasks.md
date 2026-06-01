Three most important remaining changes before m4 are:
1. Attempt parallelization 16-32 parallel pipelines and expand AXI width with successful sim and synthesis (based on current roofline results).
2. Delibreate choice must be made to cut off additional integration. PCIe is a stretch goal while AXIstream interface passes the current goal. Systolic array integration must be done by thrusday or cut. 
3. incorporate memory buffers into synthesis (currently passing simulation)
    note: current memory can likely synthesize on another platform but Openlane requires more complex custom blackbox for memory synthesis with timing.
    original platform was fpga vivado, but this whas changed to Openlane to learn
    the workflow (with SKY130 asic 130nm process (modern is >7nm) creating the current timing/clock constraint at 22ns for 32x32 multipliers). 