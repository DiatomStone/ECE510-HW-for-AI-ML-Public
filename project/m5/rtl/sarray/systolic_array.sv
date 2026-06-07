// =========================================================================
// Module:  systolic_array  (8x8 Weight-Stationary Matrix-Multiply Engine)
// Project: GELU Activation Kernel - ECE 410/510, M3 (systolic array add-on)
//
// Description:
//   N x N weight-stationary systolic array of `mac` PEs. Computes one tile of
//   a matrix product C = A * W in signed Q16.16:
//
//       C[m][n] = sum_{k=0..N-1} A[m][k] * W[k][n]
//
//   PE(r=k, c=n) holds the stationary weight W[k][n]. Activations stream in
//   from the LEFT and propagate RIGHT (one column per cycle); partial sums
//   accumulate DOWNWARD (one row per cycle) and emerge at the bottom edge.
//
//   The classic 2D dataflow needs the activations skewed (row r delayed r
//   cycles) on the way in and the column outputs de-skewed (column c delayed
//   N-1-c cycles) on the way out so that a whole A-row goes in as one vector
//   and a whole C-row comes out as one vector. Both skew triangles are kept
//   INSIDE this module, so the external interface is simply:
//       present an A-row vector  ->  (2N-1 cycles later) a C-row vector.
//
//   Tiling note: this is a single N x N tile. Larger matmuls are orchestrated
//   by the host/driver (reload weights per K-tile and accumulate the C-row
//   vectors externally, or stream successive A-rows for the M dimension). The
//   engine itself holds exactly one N x N weight tile at a time.
//
//   Vectors are packed like the v2 datapath: element i = bits [i*DW +: DW],
//   element 0 in the LSBs.
//
// Latency: out_valid (and the aligned C-row) appears LATENCY = 2*N-1 cycles
//   after in_valid is asserted with an A-row. Throughput: 1 A-row / cycle.
//
// Parameters:
//   N          - array dimension (default 8 -> 8x8)
//   DATA_WIDTH - operand/result width (default 32, Q16.16)
//   FRAC_BITS  - fractional bits (default 16)
//
// Ports:
//   clk        - input,  1            : System clock
//   rst        - input,  1            : Synchronous active-high reset
//   load_en    - input,  1            : Weight-load strobe (loads one PE row)
//   load_row   - input,  clog2(N)     : Which PE row to load this cycle
//   w_row_flat - input,  N*DW         : N weights for the selected row (lane i = W[load_row][i])
//   in_valid   - input,  1            : a_row_flat holds a valid A-row this cycle
//   a_row_flat - input,  N*DW         : A-row vector (lane k = A[m][k])
//   out_valid  - output, 1            : c_row_flat holds a valid C-row this cycle
//   c_row_flat - output, N*DW         : C-row vector (lane n = C[m][n])
// =========================================================================

module systolic_array #(
    parameter int N          = 8,
    parameter int DATA_WIDTH = 32,
    parameter int FRAC_BITS  = 16
)(
    input  logic                       clk,
    input  logic                       rst,

    // Weight load (one PE row per cycle)
    input  logic                       load_en,
    input  logic [$clog2(N)-1:0]       load_row,
    input  logic [N*DATA_WIDTH-1:0]    w_row_flat,

    // Activation stream in / result stream out
    input  logic                       in_valid,
    input  logic [N*DATA_WIDTH-1:0]    a_row_flat,
    output logic                       out_valid,
    output logic [N*DATA_WIDTH-1:0]    c_row_flat
);

    localparam int DW      = DATA_WIDTH;
    localparam int NM1     = (N > 1) ? (N - 1) : 1;   // skew/de-skew depth
    localparam int LATENCY = 2*N - 1;                 // in_valid -> out_valid

    genvar r, c, j;

    // -------------------------------------------------------------------------
    // Unpack flat vector ports into per-lane signals.
    // -------------------------------------------------------------------------
    logic signed [DW-1:0] w_arr [N];   // weights for the row being loaded
    logic signed [DW-1:0] a_arr [N];   // incoming A-row lanes
    logic signed [DW-1:0] c_arr [N];   // outgoing C-row lanes (de-skewed)

    generate
        for (c = 0; c < N; c++) begin : UNPACK
            assign w_arr[c] = w_row_flat[c*DW +: DW];
            assign a_arr[c] = a_row_flat[c*DW +: DW];
            assign c_row_flat[c*DW +: DW] = c_arr[c];
        end
    endgenerate

    // -------------------------------------------------------------------------
    // INPUT SKEW: inject A[m][r] into the left edge of row r, delayed r cycles.
    // Zeros are injected when in_valid is low so idle cycles produce zero
    // contributions (and therefore clean zero C-rows, not garbage).
    // -------------------------------------------------------------------------
    logic signed [DW-1:0] cur_in [N];          // this cycle's gated A-row
    logic signed [DW-1:0] skew   [N][NM1];      // per-row delay line (depth r used)
    logic signed [DW-1:0] a_left [N];           // left-edge injection per row

    generate
        for (r = 0; r < N; r++) begin : GATE
            assign cur_in[r] = in_valid ? a_arr[r] : '0;
        end
    endgenerate

    always_ff @(posedge clk) begin
        if (rst) begin
            for (int rr = 0; rr < N;   rr++)
                for (int jj = 0; jj < NM1; jj++)
                    skew[rr][jj] <= '0;
        end else begin
            for (int rr = 0; rr < N; rr++) begin
                skew[rr][0] <= cur_in[rr];
                for (int jj = 1; jj < NM1; jj++)
                    skew[rr][jj] <= skew[rr][jj-1];
            end
        end
    end

    generate
        for (r = 0; r < N; r++) begin : ALEFT
            if (r == 0) assign a_left[r] = cur_in[0];          // row 0: no skew
            else        assign a_left[r] = skew[r][r-1];        // row r: r-cycle skew
        end
    endgenerate

    // -------------------------------------------------------------------------
    // PE GRID: activations flow right (a_wire), partial sums flow down (p_wire).
    // -------------------------------------------------------------------------
    logic signed [DW-1:0] a_wire [N][N+1];   // a_wire[r][0]=left edge; [r][N] unused
    logic signed [DW-1:0] p_wire [N+1][N];   // p_wire[0][c]=0; [N][c]=bottom result

    generate
        for (r = 0; r < N; r++) begin : AEDGE
            assign a_wire[r][0] = a_left[r];
        end
        for (c = 0; c < N; c++) begin : PEDGE
            assign p_wire[0][c] = '0;
        end

        for (r = 0; r < N; r++) begin : ROW
            for (c = 0; c < N; c++) begin : COL
                mac #(
                    .DATA_WIDTH (DW),
                    .FRAC_BITS  (FRAC_BITS)
                ) u_pe (
                    .clk      (clk),
                    .rst      (rst),
                    .load_w   (load_en && (load_row == r[$clog2(N)-1:0])),
                    .w_in     (w_arr[c]),
                    .a_in     (a_wire[r][c]),
                    .psum_in  (p_wire[r][c]),
                    .a_out    (a_wire[r][c+1]),
                    .psum_out (p_wire[r+1][c])
                );
            end
        end
    endgenerate

    // -------------------------------------------------------------------------
    // OUTPUT DE-SKEW: bottom of column c is ready N-1-c cycles before column
    // N-1, so delay column c by (N-1-c) to align the whole C-row.
    // -------------------------------------------------------------------------
    logic signed [DW-1:0] p_bot [N];          // raw bottom-edge results
    logic signed [DW-1:0] dsk   [N][NM1];      // per-column delay line

    generate
        for (c = 0; c < N; c++) begin : PBOT
            assign p_bot[c] = p_wire[N][c];
        end
    endgenerate

    always_ff @(posedge clk) begin
        if (rst) begin
            for (int cc = 0; cc < N;   cc++)
                for (int jj = 0; jj < NM1; jj++)
                    dsk[cc][jj] <= '0;
        end else begin
            for (int cc = 0; cc < N; cc++) begin
                dsk[cc][0] <= p_bot[cc];
                for (int jj = 1; jj < NM1; jj++)
                    dsk[cc][jj] <= dsk[cc][jj-1];
            end
        end
    end

    generate
        for (c = 0; c < N; c++) begin : DESKEW
            if (c == N-1) assign c_arr[c] = p_bot[c];           // last col: no delay
            else          assign c_arr[c] = dsk[c][N-1-c-1];    // delay N-1-c cycles
        end
    endgenerate

    // -------------------------------------------------------------------------
    // VALID alignment: out_valid tracks in_valid delayed by LATENCY = 2N-1.
    // -------------------------------------------------------------------------
    logic [LATENCY-1:0] vpipe;
    always_ff @(posedge clk) begin
        if (rst) vpipe <= '0;
        else     vpipe <= {vpipe[LATENCY-2:0], in_valid};
    end
    assign out_valid = vpipe[LATENCY-1];

endmodule
