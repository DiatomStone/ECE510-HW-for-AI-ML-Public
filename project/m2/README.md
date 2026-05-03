# M2 GELU RTL

This folder contains the Milestone 2 RTL and cocotb simulation collateral for
the GELU accelerator compute core and streaming interface.

## Design Overview

The accelerator is split into two synthesizable RTL blocks:

- `rtl/compute_core.sv`: 5-stage Q16.16 fixed-point GELU pipeline.
- `rtl/interface.sv`: AXI4-Stream wrapper around the GELU compute core.

The M1 interface selection chose PCIe for host-to-accelerator communication.
For M2, the full PCIe endpoint and DMA engine are treated as external
prebuilt IP blocks. This is the usual FPGA structure: PCIe is used for
external host communication, while AXI is used for on-chip or on-board data
movement after the PCIe/DMA IP has converted host transfers into FPGA-side
transactions.

The intended hierarchy is:

1. Host CPU memory.
2. PCIe link for external communication between the host and FPGA card.
3. Vendor PCIe endpoint plus DMA IP to move large tensor bursts.
4. AXI4-Stream on-chip interface for bulk tensor data.
5. GELU AXI4-Stream interface wrapper.
6. GELU compute core.

This is why `interface.sv` implements AXI4-Stream rather than a PCIe physical
or transaction-layer interface directly. The PCIe and DMA layers sit one level
above this module. They are responsible for external communication and bulk
memory transfers; this project module is responsible for receiving stream
beats, applying GELU, and returning stream results while honoring
`TVALID/TREADY` backpressure.

This streaming structure also supports future kernel fusion. Since GELU is
memory-bound, sending every intermediate tensor back over PCIe can erase much
of the accelerator speedup. A streaming AXI interface lets future kernels stay
on the FPGA side and pass tensors directly between accelerator stages.

## Requirements

The simulations were run with:

- Icarus Verilog 12.0
- Python 3.12
- cocotb 2.0.1
- numpy 2.4.4

The workspace virtual environment used during development is located at:

```bash
/home/diatomstone/Documents/Workspace/Cursor/.venv
```

From a clean clone, install the pinned Python dependencies into a virtual
environment:

```bash
python3 -m venv .venv
.venv/bin/pip install cocotb==2.0.1 numpy==2.4.4
```

Icarus Verilog 12.0 must also be installed and available as `iverilog` and
`vvp`.

## Running Simulations

Run all commands from `project/m2`.

### Compute Core

The default Makefile target runs the compute core testbench:

```bash
PATH="../../.venv/bin:$PATH" make SIM=icarus
```

Or use the helper script:

```bash
PATH="../../.venv/bin:$PATH" ./sim_compute_core.sh
```

This writes:

- `sim/compute_core_run.log`
- `sim/compute_core_run.vcd`

Expected result:

```text
TESTS=5 PASS=5 FAIL=0
```

### AXI4-Stream Interface

The Makefile supports `opt=interface` to run the interface testbench:

```bash
PATH="../../.venv/bin:$PATH" make opt=interface SIM=icarus
```

Or use the helper script:

```bash
PATH="../../.venv/bin:$PATH" ./interface_run.sh
```

This writes:

- `sim/interface_run.log`
- `sim/interface_run.vcd`

Expected result:

```text
TESTS=1 PASS=1 FAIL=0
```

The interface test drives an AXI4-Stream input packet, applies downstream
backpressure, reads the output packet, compares GELU outputs against an
independent Python reference, and verifies `TLAST` propagation.

## Source Files

- `rtl/compute_core.sv`: GELU fixed-point compute pipeline.
- `rtl/interface.sv`: AXI4-Stream data interface around the compute core.
- `tb/tb_compute_core.py`: cocotb testbench for direct compute core testing.
- `tb/tb_interface.py`: cocotb testbench for the AXI4-Stream interface.
- `sim/compute_core_run.log`: passing compute core simulation transcript.
- `sim/interface_run.log`: passing interface simulation transcript.
- `explainations.md`: design and testbench explanation notes.

## Notes

The M2 checklist filenames mention `.sv` testbenches, but this project uses
cocotb Python testbenches. The RTL under test remains synthesizable
SystemVerilog, and the committed logs contain explicit PASS lines from cocotb.

## Deviations From M1 Plan

M1 selected PCIe as the external host interface. M2 does not implement a full
PCIe endpoint, PCIe transaction layer, or DMA engine directly in custom RTL.
Those blocks are expected to be vendor-provided IP in a practical FPGA design.

The M2 `interface.sv` module implements the FPGA-side AXI4-Stream data path
below that PCIe/DMA layer. This is consistent with the M1 PCIe direction:
PCIe handles off-board host communication, DMA moves large tensor bursts, and
AXI4-Stream carries the tensor data on chip into and out of the GELU kernel.

The kernel scope remains GELU, but the interface is intentionally streaming to
support future kernel fusion. Because GELU is memory-bound, keeping tensors on
device between fused kernels can reduce PCIe round trips and better justify the
external transfer cost.