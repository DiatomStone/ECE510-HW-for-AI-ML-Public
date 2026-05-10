# CF06 Crossbar MAC Explanations

This folder contains a small 4 by 4 binary-weight crossbar multiply-accumulate
unit and a self-checking SystemVerilog testbench.

## Main Module: `crossbar_mac.sv`

The main RTL module is `crossbar_mac`. It models a 4 input by 4 output
binary-weight crossbar MAC. The module has four signed 8-bit input lines:

- `in0`
- `in1`
- `in2`
- `in3`

It has four signed accumulator outputs:

- `out0`
- `out1`
- `out2`
- `out3`

Each output is 11 bits wide. This is enough range for the sum of four signed
8-bit values. The largest magnitude input is 128, so four terms require about
9 bits plus sign margin. Signed 11-bit output gives a range from -1024 to 1023.

## Weight Storage

The weights are stored in an internal 4 by 4 register array. Each stored
element is 2 bits wide:

```systemverilog
logic [1:0] weight_code [4][4];
```

Each stored 2-bit code represents a binary weight:

- `2'b00` means reset or neutral state, no contribution
- `2'b01` means `+1`
- `2'b11` means `-1`

The weights are loaded at runtime through the `weight_in` input vector. The
vector is 32 bits wide and interpreted row-major, so bits
`((i * 4 + j) * 2) +: 2` load `weight_code[i][j]`.

The load happens on a rising clock edge when `load_weights` is asserted:

```systemverilog
if (load_weights) begin
    weight_code[i][j] <= weight_in[((i * 4 + j) * 2) +: 2];
end
```

This satisfies the requirement that the weights are stored in a 4 by 4 register
array rather than being hard-coded only in combinational logic. Reset clears
the weight registers to `2'b00`, which is a neutral state. During the MAC, the
input is added only when the stored code is exactly `2'b01`, subtracted only
when the stored code is exactly `2'b11`, and ignored for `2'b00`.

## Input Sign Extension

The inputs are signed 8-bit numbers, but the accumulator outputs are 11 bits.
Before accumulation, each input is sign-extended:

```systemverilog
assign in_ext[0] = {{3{in0[7]}}, in0};
```

This is important because negative 8-bit inputs must remain negative after
widening. Without explicit sign extension, subtracting or adding negative
values could produce incorrect results.

## MAC Computation

The crossbar equation is:

```text
out[j] = sum_i(weight[i][j] * in[i])
```

The RTL implements this with nested loops. The outer loop selects the output
column `j`, and the inner loop walks over all four input rows `i`.

For every input and output pair:

- if the stored code is `2'b01`, the signed input is added
- if the stored code is `2'b11`, the signed input is subtracted
- if the stored code is `2'b00`, the input contributes zero

This implements multiplication by `+1` or `-1` without a hardware multiplier.

The combinational sums are stored in `sum[0]` through `sum[3]`. On every rising
clock edge, the sums are registered into `out0` through `out3`. Therefore, when
new inputs are applied before a clock edge, the matching MAC result appears on
the outputs after that clock edge.

## Testbench: `crossbar_tb.sv`

The testbench is a pure SystemVerilog self-checking testbench. It does not use
cocotb because this crossbar test is small and deterministic.

The testbench loads `crossbar_mac` with a specific weight matrix:

```text
[[ 1, -1,  1, -1],
 [ 1,  1, -1, -1],
 [-1,  1,  1, -1],
 [-1, -1, -1,  1]]
```

The corresponding `weight_in` value is:

```systemverilog
32'h7FD7F5DD
```

This value is row-major with `2'b01` meaning `+1` and `2'b11` meaning `-1`:

```text
row0 = 8'hDD = {2'b11, 2'b01, 2'b11, 2'b01}
row1 = 8'hF5 = {2'b11, 2'b11, 2'b01, 2'b01}
row2 = 8'hD7 = {2'b11, 2'b01, 2'b01, 2'b11}
row3 = 8'h7F = {2'b01, 2'b11, 2'b11, 2'b11}
```

The `load_weight_matrix` task drives `weight_in`, asserts `load_weights` for
one clock edge, then waits one additional clock so the registered weights are
stable before applying the input vector.

The testbench applies this input vector:

```text
[10, 20, 30, 40]
```

The expected output is:

```text
[-40, 0, -20, -20]
```

The hand calculation is:

```text
out0 =  10 + 20 - 30 - 40 = -40
out1 = -10 + 20 + 30 - 40 =   0
out2 =  10 - 20 + 30 - 40 = -20
out3 = -10 - 20 - 30 + 40 = -20
```

The `check_vector` task drives the inputs, waits for one clock edge, and then
compares each DUT output against the expected value. If any output is wrong,
the testbench prints a `FAIL` message and increments the failure count. If all
outputs match, it prints:

```text
PASS: crossbar_mac SystemVerilog testbench matched expected binary-weight sums
```

## Run Script: `sim_crossbar.sh`

The script compiles and runs the design directly with Icarus Verilog:

```bash
iverilog -g2012 -s crossbar_tb -o crossbar_tb.vvp crossbar_mac.sv crossbar_tb.sv
vvp crossbar_tb.vvp
```

The simulation output is saved to:

```text
crossbar_run.log
```

The temporary compiled simulation file `crossbar_tb.vvp` is deleted after the
run completes.
