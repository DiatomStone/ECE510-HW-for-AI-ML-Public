# M3_plan
- try DSP with synthesized on fpga (Boolean board Realdigial with Vivado) with existing instead of openlanes SKY130 multiplier since this was where the bottleneck was (low priority).
- ai interpretation noted alot of fanout issues which was common with SKY130 multipliers
- Perhaps the best path is to ignore the issues at worst case scenario since our operating temperature may never get there.
- focus on building the logic around the core kernel for 16x parallelization and dataflow
- in CF07 at least 10 runs were created and this module was optimized in the process by spliting to 4 stage pipeline.
- acording to amdals calculation max speedup with gelu is only ~1.264x not accounting for data transfer time so extra kernels and kernel fusion and finalization is more valuable than over optimizing gelu at this point.

```
calculation per cf02/ai_calculation.md : 131072 gelu operations to do, 10.336 seconds baseline.
at 22 ns per operation in a 4 stage pipeline (wait 4 cycles for data ):
(operations + (stage-1) )* clock period  = (131072 + (4-1)) * 22 = 2.883650 ms 
current arithmatic speedup (not accounting for data transfer) = 10.336/(0.002883650) = 3584.34x 
```
- above calculation poves that futher optimization may yeild little compared to data transfer logistics or if we focus on integrating other kernel for fusion. This is even before 16x kernel parallelization that would be (131072 + (4-1)) * 22/16 = 180.228 us, 10.336/0.000180228125  = 57350x 
- this means we only need to parallelize to match bandwidth it does not make sense to spend extra hardware area on compute when we are memory bound.

