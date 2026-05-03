# M2 Module and Testbench Explainations

This document explains the purpose and behavior of the M2 GELU compute core,
the AXI4-Stream interface wrapper, and their cocotb Python testbenches.

## Compute Core Logic: `rtl/compute_core.sv`

The `compute_core` module implements the GELU activation function:

```text
GELU(x) = 0.5 * x * (1 + tanh(sqrt(2/pi) * x + 0.044715 * sqrt(2/pi) * x^3))
```

The design uses 32-bit signed fixed-point Q16.16 arithmetic. This means the
upper 16 bits hold the signed integer portion and the lower 16 bits hold the
fractional portion. The input `x` and output `out` are both Q16.16 values.

The module is a 5-stage pipeline:

1. **Stage 1: input products**
   - Computes `x*x`, `CONST_2*x`, `CONST_1*x`, and `x >> 1`.
   - `x >> 1` implements the `0.5*x` term using an arithmetic shift.

2. **Stage 2: cubic term**
   - Multiplies `x*x` by `CONST_2*x`.
   - This produces the `CONST_2*x^3` term.
   - The linear term and half-input term are forwarded.

3. **Stage 3: polynomial sum**
   - Adds the cubic term to `CONST_1*x`.
   - The result is the input to the tanh approximation.

4. **Stage 4: piecewise-linear tanh**
   - Computes the absolute value and sign of the tanh input.
   - Uses a 10-segment piecewise-linear approximation of `tanh`.
   - Reapplies the sign after computing the positive approximation.
   - Adds `1.0` to the tanh approximation for the GELU formula.

5. **Stage 5: output multiply and saturation**
   - Multiplies `(1 + tanh(...))` by `0.5*x`.
   - Clamps the result to signed 32-bit limits if overflow occurs.
   - Drives `valid_out` aligned with the final result.

The compute core has one clock domain, `clk`, and uses a synchronous active-high
reset, `rst`. The reset clears the valid pipeline and output registers. Datapath
registers are intentionally not reset because their values only matter when
the corresponding valid bit is asserted.

## Interface Logic: `rtl/interface.sv`

The `gelu_axi_stream_interface` module wraps `compute_core` with an AXI4-Stream
data interface. This module represents the FPGA-side streaming block that would
connect to external PCIe and DMA IP. The PCIe endpoint and DMA engine are not
implemented directly in M2; they are assumed to be vendor-provided IP that
communicates with this wrapper through AXI4-Stream.

The input stream uses:

- `s_axis_tvalid`
- `s_axis_tready`
- `s_axis_tdata`
- `s_axis_tlast`
- `s_axis_tuser`

The output stream uses:

- `m_axis_tvalid`
- `m_axis_tready`
- `m_axis_tdata`
- `m_axis_tlast`
- `m_axis_tuser`

An AXI4-Stream transfer occurs only when `TVALID` and `TREADY` are both high on
the same rising clock edge. The interface converts each accepted input beat into
one `compute_core` input transaction. Each input beat contains one signed Q16.16
GELU operand.

Because `compute_core` has a fixed latency and no stall input, the wrapper adds
control logic around it:

1. **Input handshake logic**
   - `axis_in_fire` becomes true when `s_axis_tvalid && s_axis_tready`.
   - Only accepted input beats are sent into the compute core.

2. **Metadata pipeline**
   - `TLAST` and `TUSER` are delayed through a metadata pipeline matching the
     compute core latency.
   - This aligns packet metadata with the correct output result.

3. **Output FIFO**
   - Completed GELU outputs are stored in a small FIFO.
   - The FIFO also stores the aligned `TLAST` and `TUSER` bits.
   - This allows downstream DMA backpressure through `m_axis_tready` without
     losing completed compute results.

4. **Backpressure control**
   - The wrapper tracks both FIFO occupancy and in-flight operations.
   - If the total pending output capacity approaches the FIFO depth,
     `s_axis_tready` is deasserted.
   - This prevents accepting more inputs than the output side can eventually
     buffer.

This structure supports future kernel fusion because the interface is streaming.
Instead of transferring every intermediate result back to host memory over PCIe,
future kernels can be connected through AXI4-Stream so tensors remain on device
between accelerator stages.

## Compute Core Testbench: `tb/tb_compute_core.py`

The compute core testbench verifies the raw GELU pipeline without the AXI stream
wrapper. It drives the direct `valid_in`, `x`, `valid_out`, and `out` signals of
`compute_core`.

The Python reference model is independent of the RTL. It computes:

```text
0.5 * x * (1.0 + tanh(CONST_1*x + CONST_2*x^3))
```

using floating-point NumPy math. The DUT output is converted from Q16.16 back to
floating point and compared against this reference.

The testbench includes five cocotb tests:

1. **Known values test**
   - Tests representative inputs: `0.0`, `1.0`, `-1.0`, `2.0`, `-2.0`, `0.5`,
     and `-0.5`.
   - Checks each output against the Python reference.
   - Uses a 5 percent relative error tolerance for nonzero expected values.

2. **Saturation-region test**
   - Tests large inputs: `5.0`, `8.0`, `-5.0`, and `-8.0`.
   - Verifies the tanh approximation saturates correctly near `+1` or `-1`.

3. **Valid pipeline timing test**
   - Asserts `valid_in` for one cycle.
   - Checks that `valid_out` appears after the expected 5-cycle latency.
   - Confirms the valid signal is aligned with the pipelined data path.

4. **Zero input test**
   - Confirms `GELU(0)` produces approximately zero.

5. **Streaming throughput test**
   - Sends multiple inputs back-to-back.
   - Collects overlapped outputs as the pipeline fills and drains.
   - Confirms the core can accept one valid input per clock cycle.

The testbench prints expected and observed values, and cocotb reports PASS or
FAIL in `sim/compute_core_run.log`.

## Interface Testbench: `tb/tb_interface.py`

The interface testbench verifies the AXI4-Stream wrapper around `compute_core`.
It treats the DUT as a streaming accelerator block connected to an external DMA
engine.

The testbench has helper functions for complete stream transactions:

1. **`axis_send`**
   - Drives one input beat on `s_axis_tdata`.
   - Asserts `s_axis_tvalid`.
   - Waits until the DUT asserts `s_axis_tready`.
   - Completes the write-side AXI4-Stream handshake.
   - Also drives `s_axis_tlast` and `s_axis_tuser`.

2. **`axis_recv`**
   - Asserts `m_axis_tready`.
   - Waits until the DUT asserts `m_axis_tvalid`.
   - Captures `m_axis_tdata`, `m_axis_tlast`, and `m_axis_tuser`.
   - Completes the read or response-side AXI4-Stream handshake.

The main test, `test_axi_stream_gelu_packet`, sends an 8-beat packet:

```text
0.5, 1.0, 1.5, 2.0, -0.5, -1.0, -1.5, -2.0
```

This exercises multiple complete write transactions because every input beat
must complete a `TVALID/TREADY` handshake. The final input beat asserts `TLAST`
to mark the end of the packet.

The test intentionally holds `m_axis_tready` low while sending the packet. This
creates output-side backpressure and verifies that the interface FIFO buffers
completed GELU results instead of dropping them.

After the packet is sent, the testbench receives one output beat per input beat.
Each result is compared against the same independent Python GELU reference used
by the compute core testbench. The test also asserts that `TLAST` appears only
on the final output beat, proving that packet metadata is aligned with the
corresponding output data.

The interface testbench prints:

```text
PASS: AXI4-Stream GELU interface packet matched Python reference
```

when all output values and packet metadata are correct. The committed simulation
transcript is `sim/interface_run.log`.
