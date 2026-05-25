# Interface Design Explanation — gelu_axi_stream_interface

## Where This Module Sits

The full system stack looks like this:

```
Host CPU
  │  (PCIe — off-board link)
  ▼
Vendor PCIe endpoint + DMA IP        ← prebuilt IP, not our RTL
  │  (AXI4-Stream on chip)
  ▼
gelu_axi_stream_interface            ← this module
  │  (raw compute signals)
  ▼
gelu_fp32 pipeline
  └─ fp32_to_q16  →  compute_core  →  q16_to_fp32
```

The host sends FP32 tensor elements as AXI-Stream beats over PCIe/DMA. Our
module receives those beats, processes them through the GELU pipeline, and
returns results as AXI-Stream beats that the DMA engine reads back to host
memory. This module is the boundary between the transport layer and the math.

---

## Block-by-Block Walkthrough

### 1 — Module Parameters

```systemverilog
parameter int DATA_WIDTH = 32   // FP32 = 32-bit data per beat
parameter int USER_WIDTH = 1    // one sideband bit (TUSER) per beat
parameter int PIPE_DEPTH = 12   // fixed latency of gelu_fp32 in cycles
parameter int FIFO_DEPTH = 16   // entries in the output holding FIFO
```

`PIPE_DEPTH` and `FIFO_DEPTH` are tightly coupled. The backpressure scheme
works by tracking how many beats are either inside the pipeline or waiting in
the FIFO. `FIFO_DEPTH` must be at least `PIPE_DEPTH` so the FIFO can absorb
a full pipeline worth of results before the downstream consumer wakes up.

---

### 2 — AXI-Lite Slave: Write Channel (control registers)

**Ports:** `s_axil_aw*`, `s_axil_w*`, `s_axil_b*`

AXI-Lite is a simplified version of AXI4 used for slow, word-wide register
accesses — not bulk data. Here it exposes one register:

| Offset | Bits | Name            | Function                            |
|--------|------|-----------------|-------------------------------------|
| 0x00   | [0]  | pipeline_enable | 1 = accept input beats; 0 = gate off|

The write channel uses a **two-cycle handshake** (required by the AXI spec):

```
Cycle 1:  master holds awvalid=1, wvalid=1
          slave  asserts awready=1, wready=1

Cycle 2:  master still holds awvalid=1, wvalid=1 (handshake not done yet)
          slave  sees awready+awvalid together → writes the register,
                 asserts bvalid=1, deasserts awready/wready

Cycle 3:  master asserts bready=1 (already was), slave clears bvalid
```

The key spec rule: `bvalid` must not be asserted until *after* both the
address and data handshakes have completed. Asserting it in the same cycle as
`awready` would let a pipelined master sample a response before it finished
sending the request.

`wstrb[0]` gates the write — the byte-strobe signal lets the master indicate
which bytes of the 32-bit word are valid. A write with `wstrb[0]=0` leaves
the register unchanged.

---

### 3 — AXI-Lite Slave: Read Channel

**Ports:** `s_axil_ar*`, `s_axil_r*`

Same two-cycle decoupling, read direction:

```
Cycle 1:  master holds arvalid=1
          slave  asserts arready=1

Cycle 2:  master still holds arvalid=1
          slave  sees arready+arvalid → captures address, asserts rvalid+rdata,
                 deasserts arready

Cycle 3:  master asserts rready=1, slave clears rvalid; rdata holds value
```

The Icarus Verilog VPI fires `RisingEdge` callbacks before non-blocking
assignments (NBA) commit. Reading `rdata` immediately after edge 2 in the
testbench would return the stale pre-edge value. The testbench therefore
waits a third edge so edge-2's NBA has committed before sampling.

---

### 4 — Backpressure Logic

**Signals:** `in_flight_count`, `fifo_count`, `pending_count`, `s_axis_tready`

The GELU pipeline has no stall input — once a beat enters, it exits exactly
`PIPE_DEPTH` cycles later regardless of what the downstream consumer is doing.
If the output FIFO fills up and a result arrives with nowhere to go, data is
lost.

The solution: count how many beats are "in the system" at all times.

```
pending_count = in_flight_count + fifo_count
```

- `in_flight_count`: beats currently inside the gelu_fp32 pipeline (entered
  but not yet emerged).
- `fifo_count`: beats sitting in the output FIFO waiting to be read.

`s_axis_tready` is deasserted as soon as `pending_count` reaches `FIFO_DEPTH`:

```systemverilog
assign s_axis_tready = pipeline_enable && (pending_count < FIFO_DEPTH);
```

This stops the master from sending more beats before there is room for the
results. Because the pipeline has fixed latency, we know exactly when each
in-flight beat will land in the FIFO, so we can count conservatively and
guarantee zero overflow.

```
in_flight_count update:
  +1 when a beat enters the pipeline (axis_in_fire)
  -1 when a result exits the pipeline (core_valid_out)

fifo_count update:
  +1 when a result is written into the FIFO (core_valid_out)
  -1 when a beat is read out of the FIFO (axis_out_fire = m_axis_tvalid && m_axis_tready)
```

Both increments and decrements can happen in the same cycle (a result lands
in the FIFO exactly as another is read out) — the case statement handles that
cleanly with a no-change default.

---

### 5 — gelu_fp32 Core Instantiation

```systemverilog
gelu_fp32 u_gelu_fp32 (
    .clk       (clk),
    .rst       (rst),
    .valid_in  (axis_in_fire),    // fire only on a real handshake
    .data_in   (s_axis_tdata),
    .valid_out (core_valid_out),
    .data_out  (core_data_out)
);
```

`axis_in_fire = s_axis_tvalid && s_axis_tready` — the pipeline only advances
when both sides of the handshake agree. `valid_in` propagates through all
12 stages as a validity flag so the output FIFO knows when a real result has
arrived versus a pipeline bubble.

Inside `gelu_fp32`:
- **fp32_to_q16** (4 cycles): IEEE-754 FP32 → Q16.16 fixed-point
- **compute_core** (4 cycles): 20-segment PWL GELU approximation in Q16.16
- **q16_to_fp32** (4 cycles): Q16.16 → IEEE-754 FP32

---

### 6 — Metadata Pipeline: TLAST and TUSER

```systemverilog
logic [PIPE_DEPTH-1:0] meta_tlast_pipe;
logic [USER_WIDTH-1:0] meta_tuser_pipe [PIPE_DEPTH];
```

The gelu_fp32 pipeline carries only data and valid — it has no sideband
signals. TLAST (end-of-packet marker) and TUSER (arbitrary sideband) must
travel alongside each beat and emerge from the output at the correct time.

This is a simple 12-tap shift register. Every clock cycle, a new entry enters
at position 0 (holding the TLAST/TUSER of the beat that just fired into the
pipeline, or zeros if no beat fired), and all entries shift up by one. After
12 cycles the metadata appears at position `PIPE_DEPTH-1` exactly when
`core_valid_out` fires for the corresponding data beat.

Because the pipeline has no stall logic, the shift register advances every
clock cycle unconditionally — it stays perfectly aligned with the pipeline
stages. If stall logic were ever added, the shift enable would need to match.

---

### 7 — Output FIFO

```systemverilog
logic [DATA_WIDTH-1:0] fifo_data  [FIFO_DEPTH];
logic                  fifo_tlast [FIFO_DEPTH];
logic [USER_WIDTH-1:0] fifo_tuser [FIFO_DEPTH];
logic [PTR_W-1:0]      fifo_wr_ptr;
logic [PTR_W-1:0]      fifo_rd_ptr;
```

A circular buffer with separate read and write pointers. Depth is 16, so the
pointer is 4 bits; it wraps naturally at 16 because 4-bit addition overflows.

**Write side** (driven by the pipeline): when `core_valid_out` is high, data,
TLAST, and TUSER are written at `fifo_wr_ptr`, then the pointer increments.

**Read side** (driven by the downstream consumer): the output signals are
driven combinationally from `fifo_rd_ptr` — an asynchronous read:

```systemverilog
assign m_axis_tdata  = fifo_data[fifo_rd_ptr];
assign m_axis_tlast  = fifo_tlast[fifo_rd_ptr];
assign m_axis_tvalid = (fifo_count != 0);
```

Async read means there is no extra cycle of latency to get data out. The
synthesis tool infers this as distributed RAM (LUTRAM) rather than a
synchronous block RAM, which is optimal for a 16-entry FIFO.

When `m_axis_tvalid && m_axis_tready` (the downstream consumer accepts a
beat), `fifo_rd_ptr` increments and `fifo_count` decrements.

---

## Signal Flow Summary

```
s_axis_tdata ──► gelu_fp32 ──► core_data_out ──► fifo_data[] ──► m_axis_tdata
                                                                       ▲
s_axis_tlast ──► meta_tlast_pipe[11:0] ──────────────────────► fifo_tlast[]
s_axis_tuser ──► meta_tuser_pipe[11:0] ──────────────────────► fifo_tuser[]

s_axis_tready ◄── pipeline_enable && (pending_count < FIFO_DEPTH)
                                              ▲
              in_flight_count + fifo_count ───┘

s_axil_wdata[0] ──► pipeline_enable ──────────────────────────────────┘

m_axis_tvalid ◄── (fifo_count != 0)
m_axis_tready ──► drains fifo, decrements fifo_count
```
