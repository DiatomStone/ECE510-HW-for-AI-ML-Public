#!/bin/bash
check(){
ls "$1" > /dev/null
}
cd ..
#cf04
ls codefest/errorcheck > /dev/null
ls codefest/cf04/hdl/mac_llm_A.*> /dev/null
ls codefest/cf04/hdl/mac_llm_B.*> /dev/null
ls codefest/cf04/hdl/mac_tb.*> /dev/null
ls codefest/cf04/hdl/mac_correct.*> /dev/null
ls codefest/cf04/review/mac_code_review.md > /dev/null
ls codefest/cf04/cman_quantization.md > /dev/null
ls codefest/cf04/cocotb_mac/test_mac.py > /dev/null
ls codefest/cf05/cman_systolic_trace.md > /dev/null
check codefest/cf07/cman_sparsity_analysis.md
check codefest/cf07/hdl/synth_top.sv 
check codefest/cf07/synth/metrics.csv
check codefest/cf07/synth/synth_interpretation.md
check codefest/cf07/synth/m3_plan.md
check project/scope_assessment.md
check codefest/cf09/cman_ai_analysis.md
check codefest/cf09/cman_roofline_sketch.pdf
check codefest/cf09/benchmarks/benchmark_results.md
check codefest/cf09/benchmarks/roofline_plot.png
check project/remaining_tasks.md
check codefest/cf09/benchmarks/roofline_analysis.md
read -p "[Enter] to exit"
