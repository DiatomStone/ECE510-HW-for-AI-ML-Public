`timescale 1ns/1ps

module mac_tb;

    // ----------------------------------------------------------------
    // DUT signals
    // ----------------------------------------------------------------
    logic        clk;
    logic        rst;
    logic signed [7:0]  a;
    logic signed [7:0]  b;
    logic signed [31:0] out;

    // ----------------------------------------------------------------
    // Instantiate DUT
    // ----------------------------------------------------------------
    mac dut (
        .clk (clk),
        .rst (rst),
        .a   (a),
        .b   (b),
        .out (out)
    );

    // ----------------------------------------------------------------
    // Clock: first posedge at t=5ns
    // ----------------------------------------------------------------
    initial clk = 0;
    always #5 clk = ~clk;

    // ----------------------------------------------------------------
    // Reference model & check task
    // ----------------------------------------------------------------
    logic signed [31:0] expected;

    task automatic check(input string label);
        #1; // sample 1ps after rising edge
        if (out !== expected)
            $error("[FAIL] %s | got out=%0d, expected=%0d", label, out, expected);
        else
            $display("[PASS] %s | a=%0d, b=%0d, out=%0d", label, a, b, out);
    endtask

    // ----------------------------------------------------------------
    // Stimulus
    // ----------------------------------------------------------------
    initial begin
        // Assert rst=1 at t=0 (before the first posedge at t=5)
        // so the very first clock edge latches a clean 0.
        rst      = 1;
        a        = 0;
        b        = 0;
        expected = 0;

        @(posedge clk); // t=5ns  → out becomes 0
        #1; // confirm reset took effect
        rst = 0;

        // ============================================================
        // PHASE 1: a=3, b=4 for 3 cycles
        //   After cycle 1: out =  0 + 12 =  12
        //   After cycle 2: out = 12 + 12 =  24
        //   After cycle 3: out = 24 + 12 =  36
        // ============================================================
        $display("\n=== PHASE 1: a=3, b=4 for 3 cycles ===");
        a = 8'sd3;
        b = 8'sd4;

        @(posedge clk); expected += (32'sd3 * 32'sd4); check("Cycle 1 | a= 3, b= 4");
        @(posedge clk); expected += (32'sd3 * 32'sd4); check("Cycle 2 | a= 3, b= 4");
        @(posedge clk); expected += (32'sd3 * 32'sd4); check("Cycle 3 | a= 3, b= 4");

        // ============================================================
        // PHASE 2: assert rst for 1 cycle (synchronous reset)
        //   Rising edge while rst=1 → out becomes 0
        // ============================================================
        $display("\n=== PHASE 2: rst asserted (1 cycle) ===");
        rst      = 1;
        expected = 0;

        @(posedge clk); check("Reset cycle           ");

        // ============================================================
        // PHASE 3: a=-5, b=2 for 2 cycles
        //   After cycle 1: out =   0 + (-10) = -10
        //   After cycle 2: out = -10 + (-10) = -20
        // ============================================================
        $display("\n=== PHASE 3: a=-5, b=2 for 2 cycles ===");
        rst = 0;
        a   = -8'sd5;
        b   =  8'sd2;

        @(posedge clk); expected += (-32'sd5 * 32'sd2); check("Cycle 1 | a=-5, b= 2");
        @(posedge clk); expected += (-32'sd5 * 32'sd2); check("Cycle 2 | a=-5, b= 2");

        $display("\n=== Done. Final accumulator = %0d ===\n", out);
        $finish;
    end

    // ----------------------------------------------------------------
    // Timeout watchdog
    // ----------------------------------------------------------------
    initial begin
        #10_000;
        $error("TIMEOUT: simulation exceeded 10 us");
        $finish;
    end

endmodule
