## LLM sources
| LLM | Model | File | 
|-----|-------|------|
| A | Claude Sonnet 4.6 | `mac_llm_A.sv` | 
| B | Gemini Fast | `mac_llm_B.sv` | 
| C | GPT-5.3 | `mac_llm_C.sv` | 
| D | gemma4:26b-a4b-it-q4_K_M (Local) | `mac_llm_D.sv` | 
| E | gemma4:e4b (Local) | `mac_llm_E.sv` | 

## Prompt for both/all llm
Module name: mac
Inputs: clk (1-bit), rst (1-bit, active-high synchronous reset), a (8-bit signed), b (8-bit
signed)
Output: out (32-bit signed accumulator)
Behavior: On each rising clock edge: if rst is high, set out to 0; else add a×b to out.
Constraints: Synthesizable SystemVerilog only. No initial blocks, no $display, no delays
(#). Use always_ff


## Errors
Both Claude sonnet and Gemini pased without error from verilator. Additionally Chat gpt was used in llm C. All 3 Free AI generated a correct output when verified with verilator --lint-only. There was not any errors to correct however bellow is a way to prompt the ai to perhaps improve acuracy. All 3 models produced the same module. Local llm gemma4:26b-a4b-it-q4_K_M and gemma4:e2b was used with ollama to generate MAC, the results of the quantized gemma 4 26b model were the same as cloud llm. However gemma4:e4b resulted in missing ```logic``` keyword in ports, this resulted in interpretation of ```out``` as wires.

### linting gemma4:e4b error: 
```Error
%Error-PROCASSWIRE: ../mac_llm_E.sv:13:13: Procedural assignment to wire, perhaps intended var (IEEE 1800-2023 6.5): 'out'
                                         : ... note: In instance 'mac'
   13 |             out <= 32'd0;
      |             ^~~
                    ... For error description see https://verilator.org/warn/PROCASSWIRE?v=5.046
%Error-PROCASSWIRE: ../mac_llm_E.sv:18:13: Procedural assignment to wire, perhaps intended var (IEEE 1800-2023 6.5): 'out'
                                         : ... note: In instance 'mac'
   18 |             out <= out + (a * b);
      |             ^~~
```
- **(a) offending line**: 6 | `output signed [31:0] out`
- **(b) issue explaination**:missing `logic` keyword in ports, this resulted in interpretation of `out` as wires.
- **(c) corrected version**: `output logic signed [31:0] out`, also logic should be added to inputs as well  

`mac_correct.v` uses `mac_llm_A.sv` which is the same for A-D versions
## potential prompt for llm to improve accuracy
Task: Generate system verilog HDL of a multiply accumulator
AI rules: 
1. ports must be:
inputs: clk (1-bit), rst (1-bit, active-high synchronous reset), a (8-bit signed), b (8-bit signed). 
output: out (32-bit signed accumulator)
2. reset behavior: On each rising clock edge: if rst is high, set out to 0; else add a×b to out
3. at each clock cycle output port: 
4. Synthesizable SystemVerilog only. No initial blocks, no $display, no delays(#). Use always_ff.
5. set module name: mac
6. Think very hard to get correct result.

## Verilator Simulation results.
simulation log is located in [simulation.log](../hdl/script/simulation.log)

Result of simulation on correct llm: 
```
=== PHASE 1: a=3, b=4 for 3 cycles ===
[PASS] Cycle 1 | a= 3, b= 4 | a=3, b=4, out=12
[PASS] Cycle 2 | a= 3, b= 4 | a=3, b=4, out=24
[PASS] Cycle 3 | a= 3, b= 4 | a=3, b=4, out=36

=== PHASE 2: rst asserted (1 cycle) ===
[PASS] Reset cycle            | a=3, b=4, out=0

=== PHASE 3: a=-5, b=2 for 2 cycles ===
[PASS] Cycle 1 | a=-5, b= 2 | a=-5, b=2, out=-10
[PASS] Cycle 2 | a=-5, b= 2 | a=-5, b=2, out=-20

=== Done. Final accumulator = -20 ===
```

## Yosys synthesis result
Full output can be found in [synth_yosys.log](../hdl/script/synth_yosys.log)

```Yosys output
=== mac ===

        +----------Local Count, excluding submodules.
        | 
      946 wires
     1177 wire bits
        5 public wires
       50 public wire bits
        5 ports
       50 port bits
      999 cells
      330   $_ANDNOT_
       46   $_AND_
        1   $_MUX_
       32   $_NAND_
       66   $_NOR_
       17   $_NOT_
       89   $_ORNOT_
       49   $_OR_
       32   $_SDFF_PP0_
       86   $_XNOR_
      251   $_XOR_
```
