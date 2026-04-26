LLM A: Claude sonnet 4.6
LLM B: Gemini Fast

Prompting guidance
Structure your prompt with:
(1) the exact module signature including port names and bit widths;
(2) reset behavior (synchronous, active-high);
(3) what the output register should do each clock cycle;
(4) an explicit request for synthesizable SystemVerilog only — no initial blocks, no $display, nodelays.

## Same prompt for both llm
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

## Errors
Both Claude sonnet and Gemini pased without error from verilator