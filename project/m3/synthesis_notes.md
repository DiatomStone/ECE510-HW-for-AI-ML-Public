# Synthesis 
All modules passed synthesis: 
- Axis/axil interface 
- fp32 to q16
- core pwl gelu kernel
- p16 to fp32

In the previous CF07 setup time failed for the core kernel. To mitigate this the 3 stage PWL gelu was transfered into 4 stage. With the longest path 32x32 bit multiplication split into 2 stages. the Q16.16 shift of fraction bits was also moved forward in stage 4. Early explicit casting resulted in 64x64 multiplication hardware being used so that was removed to let the compiler handle the multiplication hardware instead. 

Adding floating point conversion and axi at the interface level seems to pass timing at 22 ns period. However slew warning was noted in the log at 100c and 1v60, the Openlane internal check right after showed that there was no error, per Claude. No error was noted in the error log. Even if this was a misinterpretation by claude and there was a slew violation, ss_100c_1v60 represent extreme environmental case. As mentioned in CF07, this logged violation was was a operation condition threashold beyond my target; this is expected to be fixable by lowering down the clock.

The longest path was noted was from s2_m to s3_mult. This was the same as the previous itteration at cf07. This tells me that after running synthesis there was no longer path (timing violations) by placed logic in the conversion steps or the Axi interface. 

Key to the success was running this with the gelu kernel alone first. Before synthesis, functional rtl was verified with simulation. This was the most challenging step since many itterations were needed. Further more it was found that using multiple AI (gemini PRO) gave insight that the current AI context missed: this resulted in verification insight that there was a mismatch between synthesis functional RTL and the nuance of AXI protocol. Simulation of each part was done individually for modules and each needed to pass simulation before moving on. This prevented the issue of finding something later in simulation and having to run synthesis again and reckeck timing or some other issue may arise. Iteration was the reason for the simulation helper_scripts. Synthesis was reran after the final co_simulation to make sure no changes made to HDL affected the P&R.

## Result Summary (RUN_2026-05-24_21-40-35)

| Metric | Value |
|--------|-------|
| Flow result | Complete (exit 0, 78 steps, 6:58) |
| LVS / DRC / Antenna | All passed |
| Setup violations | 0 across all 9 corners |
| Hold violations | 0 across all 9 corners |
| Critical path (nom TT) | 10.174 ns — slack +11.83 ns |
| Clock period | 22 ns |
| Total cell area | 90,470 µm² |
| Flip-flops | 1,142 |
| Total power (nom TT) | 30.22 mW |
| Max-slew warnings | ss_100C_1v60 corners only (extreme corner) |

# Scope adjustments
In tb_top.py the PCIe/DMA as well as AXI memory backend was simulated using cocotb's IP, this current form contains timed DMA controled axi transfers between memory and our Kernel.  RTL contains up to AXI, custom HDL DMA and PCIe and memory may be possible however my core interest is creating an acceleration kernel with an interface. AXI seems to be widely accepted as an onchip interface. The current scope is functional cosimulation with AXI, with gen_vector.py creating input values that would be created by transformer_ml.py. As an end product this would be useful since we can integrate the AXI stream/lite GELU module (as a chiplet) into a larger AXI communication based chiplet. 

As mentioned in the cf07, the original plan was to instantiate this module 16x in parallel, however speedup calculation showed that with one module already gives x3000 speedup at the synthesized 22 ns; 16 module yeilds about x55000 speedup. This compute speed is expected to by far exceed bandwidth limits. So the adjusted plan is instantiate just one GELU pipeline and increase only with bandwith availablility. 

Further clarification is required if the DMA RTL is needed cocotbext-PCIe should be used. If there is available time, I will proceed with implementing the feed forward loop ( weight stationary systolic array) after the FP32_P16 and before the PWL GELU.  
Next step would be in-loop simulation and timing measuremet.s 
