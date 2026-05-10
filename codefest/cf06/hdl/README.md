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

The weights are stored in an internal 4 by 4 register array:

```systemverilog
logic weight_bit [4][4];
```

Each stored bit represents a binary weight:

- `1'b1` means `+1`
- `1'b0` means `-1`

The weights are loaded at runtime through the `weight_in` input vector. The
vector is interpreted row-major, so bit `(i * 4) + j` loads
`weight_bit[i][j]`.

The load happens on a rising clock edge when `load_weights` is asserted:

```systemverilog
if (load_weights) begin
    weight_bit[i][j] <= weight_in[(i * 4) + j];
end
```

This satisfies the requirement that the weights are stored in a 4 by 4 register
array rather than being hard-coded only in combinational logic. Reset clears
the weight registers to zero, which corresponds to all weights being `-1`,
until the testbench or another controller loads a new vector.

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

- if the weight bit is `1`, the signed input is added
- if the weight bit is `0`, the signed input is subtracted

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
16'h8635
```

This value is row-major with `1` meaning `+1` and `0` meaning `-1`:

```text
row0 = 0101
row1 = 0011
row2 = 0110
row3 = 1000
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
