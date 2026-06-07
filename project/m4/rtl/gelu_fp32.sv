// =========================================================================
// Module:  gelu_fp32
// Project: GELU Activation Kernel - ECE 410/510, M3
//
// Description:
//   End-to-end FP32 GELU datapath. Chains three pipelined sub-modules:
//
//     fp32_to_q16 (4 stages) -> compute_core (4 stages) -> q16_to_fp32 (4 stages)
//
//   Total latency: 12 clock cycles from valid_in to valid_out.
//   Full throughput: one result per cycle once the pipeline is filled.
//   This module is a pure datapath; all AXI handshaking is handled by the
//   enclosing gelu_axi_stream_interface.
//
// Clock Domain:
//   Single clock domain (clk). All sequential logic on posedge clk.
//
// Reset:
//   Synchronous, active-high (rst).
//
// Ports:
//   clk       - input,  1   : System clock
//   rst       - input,  1   : Synchronous active-high reset
//   valid_in  - input,  1   : Asserted when data_in holds a valid FP32 operand
//   data_in   - input,  32  : IEEE-754 single-precision input value
//   valid_out - output, 1   : Asserted when data_out holds a valid FP32 result
//   data_out  - output, 32  : IEEE-754 single-precision GELU(data_in) result
// =========================================================================

module gelu_fp32 (
    input  logic        clk,
    input  logic        rst,

    // FP32 input
    input  logic        valid_in,
    input  logic [31:0] data_in,

    // FP32 output
    output logic        valid_out,
    output logic [31:0] data_out
);

    // -------------------------------------------------------------------------
    // Stage 1 → Stage 2 wires  (fp32_to_q16 → synth_top)
    // -------------------------------------------------------------------------
    logic        s1_valid;
    logic [31:0] s1_data;   // Q16.16 signed fixed-point

    // -------------------------------------------------------------------------
    // Stage 2 → Stage 3 wires  (synth_top → q16_to_fp32)
    // -------------------------------------------------------------------------
    logic        s2_valid;
    logic [31:0] s2_data;   // Q16.16 signed fixed-point GELU result

    // -------------------------------------------------------------------------
    // fp32_to_q16 : IEEE-754 FP32 → Q16.16
    // -------------------------------------------------------------------------
    fp32_to_q16 u_fp32_to_q16 (
        .clk       (clk),
        .rst       (rst),
        .valid_in  (valid_in),
        .data_in   (data_in),
        .valid_out (s1_valid),
        .data_out  (s1_data)
    );

    // -------------------------------------------------------------------------
    // compute_core : Q16.16 GELU PWL approximation
    // -------------------------------------------------------------------------
    compute_core #(
        .DATA_WIDTH (32),
        .FRAC_BITS  (16),
        .PIPE_DEPTH (4)
    ) u_synth_top (
        .clk       (clk),
        .rst       (rst),
        .valid_in  (s1_valid),
        .x         (s1_data),
        .valid_out (s2_valid),
        .out       (s2_data)
    );

    // -------------------------------------------------------------------------
    // q16_to_fp32 : Q16.16 → IEEE-754 FP32
    // -------------------------------------------------------------------------
    q16_to_fp32 u_q16_to_fp32 (
        .clk       (clk),
        .rst       (rst),
        .valid_in  (s2_valid),
        .data_in   (s2_data),
        .valid_out (valid_out),
        .data_out  (data_out)
    );

endmodule
