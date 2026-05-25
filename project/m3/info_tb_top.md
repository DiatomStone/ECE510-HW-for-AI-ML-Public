# info_tb_top — Annotated walkthrough of tb_top.py

This file maps each region of `tb_top.py` to the equivalent hardware block it
represents, and identifies exactly where a PCIe/DMA backend and an AXI memory
model would live in a real or extended simulation.

---

## System Architecture — what the testbench models

```
┌─────────────────────────────────────────────────────────────────────────┐
│  HOST (CPU / PCIe Root Complex)                                         │
│                                                                         │
│   train.py / inference code                                             │
│       │  calls gelu(h)  →  wants hardware result back                  │
│       ▼                                                                 │
│   PCIe DMA engine  ◄──── [REGION 2 & 4 in tb_top.py]                  │
│       │  issues DMA write (input data → device memory)                 │
│       │  issues DMA read  (output data ← device memory)                │
└───────┼─────────────────────────────────────────────────────────────────┘
        │  PCIe TLP (Memory Write / Read)
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  DEVICE (FPGA / ASIC)                                                   │
│                                                                         │
│  ┌──────────────┐    AXI4-MM     ┌──────────────────────────────────┐  │
│  │  PCIe EP /   │◄──────────────►│  AXI Memory (BRAM / DRAM ctrl)  │  │
│  │  DMA engine  │                │  INPUT_BASE  = 0x0000_0000       │  │
│  └──────┬───────┘                │  OUTPUT_BASE = 0x0001_0000       │  │
│         │ AXI4-Lite (config)     └──────────────┬───────────────────┘  │
│         │                                        │ AXI4-MM read/write   │
│         ▼                                        ▼                      │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  DMA Controller                                                  │   │
│  │   - reads  INPUT_BASE  → drives AXI-Stream to gelu_top          │   │
│  │   - captures AXI-Stream from gelu_top → writes OUTPUT_BASE      │   │
│  └──────────────────────┬────────────────────┬──────────────────────┘   │
│             s_axis (in) │                    │ m_axis (out)             │
│                         ▼                    ▼                          │
│                  ┌──────────────────────────────────┐                   │
│                  │         gelu_top  (RTL DUT)       │                   │
│                  │   s_axil ── AXI-Lite ctrl CSRs   │                   │
│                  │   s_axis ── FP32 input stream     │                   │
│                  │   m_axis ── FP32 GELU output      │                   │
│                  └──────────────────────────────────┘                   │
└─────────────────────────────────────────────────────────────────────────┘
```

In `tb_top.py` the blocks above the DUT are all Python coroutines.
The DUT (`gelu_top`) is the only block that runs as actual RTL in Icarus.

---

## Region 1 — AXI-Lite control register write

**What it models**

The host writing a configuration register over PCIe. In a real system the
DMA engine would issue an AXI4-Lite (or APB) write to the accelerator's
control register bank. Here the cocotb `AxiLiteMaster` drives the `s_axil`
port of `gelu_top` directly.

- Register written: offset `0x00` ← `pipeline_enable`
- Value: `0x0000_0001` ← enable = 1

**In tb_top.py:**

```python
await axil_master.write(0x00, b'\x01\x00\x00\x00')
readback = await axil_master.read(0x00, 4)
assert readback.data == b'\x01\x00\x00\x00'
```

**Real system equivalent**

PCIe root complex issues a Memory Write TLP to the BAR-mapped CSR address.
The PCIe endpoint decodes it and issues an AXI4-Lite write to the accelerator.
The readback is a Memory Read TLP → AXI4-Lite read.

**To extend:** replace `AxiLiteMaster` with a PCIe TLP generator (e.g.
`cocotbext-pcie`) targeting a BAR, backed by an AXI4-Lite bridge.

---

## Region 2 — Host DMA write (input vectors → device memory)

**What it models**

The host CPU issuing a DMA transfer that copies the input tensor from host
RAM into the device-side AXI memory buffer (BRAM / off-chip DRAM).

**Memory model in tb_top.py:**

```python
mem = bytearray(MEM_SIZE)   # 128 KB flat address space
                             # INPUT_BASE  = 0x0000_0000
                             # OUTPUT_BASE = 0x0001_0000
```

**The "DMA write" in tb_top.py:**

```python
for i, h in enumerate(in_hex):
    chunk = hex_to_bytes_le(h)
    mem[INPUT_BASE + i*4 : INPUT_BASE + i*4 + 4] = chunk
```

This is a direct Python byte-slice write — it represents the moment the
PCIe DMA engine finishes copying the input data into device memory.
No clock cycles are consumed; the memory is pre-loaded before simulation
time advances.

### Where the AXI memory lives

The `mem` bytearray **is** the AXI memory model. In `tb_top.py` it is a plain
Python buffer. To make it a proper AXI4-MM slave (so a DMA RTL block could
read/write it over a bus):

```python
from cocotbext.axi import AxiRam
axi_ram = AxiRam(AxiBus.from_prefix(dut, "m_axi"), dut.clk, dut.rst,
                 size=MEM_SIZE)
axi_ram.write(INPUT_BASE, input_bytes)   # pre-load, same as now
```

The `AxiRam` model then responds to AXI4 read/write transactions from a DMA
controller RTL module wired to `gelu_top`.

### Where the PCIe / DMA backend lives

The Python for-loop above is a stand-in for:

```
PCIe root complex (host)
    └─► PCIe endpoint (device, RTL or model)
            └─► AXI4 Master (DMA engine RTL)
                    └─► AxiRam slave  ←  this is the AXI memory
```

Using `cocotbext-pcie`, the host side would instead do:

```python
await dev.dma_mem.write(host_buf_addr, input_bytes)
# DMA engine issues AXI4 bursts → AxiRam.write at INPUT_BASE
```

Nothing in `gelu_top.sv` needs to change for this extension.

---

## Region 3 — DMA transfer (memory ↔ AXI-Stream ↔ DUT)

**What it models**

The DMA controller on the device reading from AXI memory and streaming data
through the GELU accelerator, then writing results back to memory. This is the
**only region where simulation time (clock cycles) advances**.

**Two coroutines run concurrently in tb_top.py:**

```python
recv_task = cocotb.start_soon(dma_from_stream(...))   # arm first
send_task = cocotb.start_soon(dma_to_stream(...))     # then send
await send_task
await recv_task
```

### `dma_to_stream`

Reads `n_beats × 4` bytes from `mem[INPUT_BASE]` and calls
`axis_source.write()` which drives `s_axis_tdata/tvalid/tlast` on `gelu_top`.

Real system equivalent: DMA controller RTL reads `INPUT_BASE` from `AxiRam`
over an AXI4-MM burst, then issues AXI-Stream beats to `s_axis` of `gelu_top`.

### `dma_from_stream`

Calls `axis_sink.recv()` which blocks until `gelu_top` asserts `m_axis_tlast`,
then writes the received bytes into `mem[OUTPUT_BASE]`.

Real system equivalent: DMA controller RTL accepts AXI-Stream beats from
`m_axis` of `gelu_top` and writes them to `OUTPUT_BASE` in `AxiRam` over an
AXI4-MM burst.

The `gelu_top` DUT sees only AXI-Stream handshakes — identical in both the
Python and RTL DMA cases. This is why no RTL changes are needed for the memory
layer extension.

### Concurrent execution note

`recv_task` is started **before** `send_task`. This matters because `gelu_top`
has a 12-cycle pipeline. If `recv_task` were started after `send_task`, the
first output beats could arrive at `m_axis` before the sink is armed, and the
handshake would stall until the FIFO inside `gelu_top` fills up. Starting
`recv_task` first ensures `m_axis_tready` is asserted from cycle 0.

---

## Region 4 — Host DMA read (device memory → verification)

**What it models**

The host CPU issuing a DMA read that transfers the output tensor from device
memory back to host RAM for comparison against the software reference.

**In tb_top.py:**

```python
b_chunk = bytes(mem[OUTPUT_BASE + i*4 : OUTPUT_BASE + i*4 + 4])
got_r   = bytes_le_to_float(b_chunk)
exp_r   = bytes_le_to_float(hex_to_bytes_le(exp_hex[i]))
```

The slice read from `mem` is the Python equivalent of:

```
PCIe DMA read TLP  →  AXI4-MM read from AxiRam[OUTPUT_BASE]
→  data returned to host buffer  →  compared against gelu_exp.hex
```

`gelu_exp.hex` is the independent software reference produced by
`gen_vectors.py` (float64 GELU on the same FP32 inputs). It plays the role of
the software model output that the host would compare against in a real
in-loop co-simulation.

PASS/FAIL threshold: `abs(got - exp) <= 0.05` for all 256 outputs.

---

## Summary — Python vs RTL

| Block | Current `tb_top.py` | Path B extension |
|-------|---------------------|------------------|
| `gelu_top` DUT | Icarus RTL ✓ | Icarus RTL ✓ |
| AXI-Lite master (config) | `cocotbext-axi` VIP | `cocotbext-axi` VIP |
| AXI memory (BRAM model) | Python `bytearray` | `cocotbext-axi` `AxiRam` |
| DMA to-stream controller | Python coroutine | RTL `dma_controller.sv` |
| DMA from-stream controller | Python coroutine | RTL `dma_controller.sv` |
| PCIe endpoint / TLP engine | implicit (direct writes) | `cocotbext-pcie` |
| Host DMA engine | implicit (direct reads) | `cocotbext-pcie` |

The boundary between host and device in the current setup is the
`INPUT_BASE` / `OUTPUT_BASE` addresses in `mem`. Everything above that
boundary (Regions 2 and 4) is host-side. Everything below (Region 3 and
the DUT) is device-side.


What the current testbench already times

Only Region 3 (dma_to_stream / dma_from_stream + the DUT) consumes simulation clock cycles. Regions 2 and 4 are instantaneous Python byte-slice operations — zero simulated time.

---
Option A — Analytical PCIe overhead (easiest, no RTL change)

Measure Region 3 with cocotb.utils.get_sim_time(), then add the PCIe/DMA transfer time as a formula:

from cocotb.utils import get_sim_time

# Region 3 — actual kernel timing
t0 = get_sim_time(units="ns")
recv_task = cocotb.start_soon(dma_from_stream(...))
send_task = cocotb.start_soon(dma_to_stream(...))
await send_task
await recv_task
kernel_ns = get_sim_time(units="ns") - t0

# PCIe analytical model
N_bytes       = N * 4                      # e.g. 256 * 4 = 1024 B
PCIE_BW_GBs   = 16.0                       # PCIe Gen3 x4 effective ~16 GB/s
PCIE_LATENCY  = 1000                       # ~1 µs base latency in ns
pcie_xfer_ns  = (N_bytes / (PCIE_BW_GBs * 1e9)) * 1e9 + PCIE_LATENCY

total_ns = pcie_xfer_ns  # DMA write (in)
         + kernel_ns      # kernel execution
         + pcie_xfer_ns   # DMA read (out)

This is realistic for small payloads (your 1 KB case is dominated by PCIe latency, not bandwidth).

---
Option B — Inject Timer delays into Regions 2 & 4

Make the testbench actually consume simulation time fhe Python byte loops into await Timer(...) calls:

# Region 2: model DMA write latency
N_bytes = N * 4
pcie_ns = int((N_bytes / (16e9)) * 1e9) + 1000   # la
for i, h in enumerate(in_hex):
    mem[INPUT_BASE + i*4 : INPUT_BASE + i*4 + 4] = hex_to_bytes_le(h)
await Timer(pcie_ns, unit="ns")   # <-- consumes sim
Do the same at the end of Region 4. Then get_sim_timend end of Region 4 gives you the total end-to-end walltime inclusive of PCIe.

---
Which to use

┌─────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────┐
│                      Goal                       │  pproach                               │
├─────────────────────────────────────────────────┼────────────────────────────────────────┤
│ Report kernel-only cycles (hardware efficiency) │ Ort separately                         │
├─────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
│ Report full host-to-host latency in waveform    │ O in VCD                               │
├─────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
│ True PCIe cycle-accurate timing                 │ Fnt effort, overkill for this project) │
└─────────────────────────────────────────────────┴─────────────────────────────────────────────────────────────────────┘

For an ECE 510 project, Option A is the right call: mion 3 directly, then add the analytical PCIe overheadin your report. The numbers will be accurate and honeactually exercises.