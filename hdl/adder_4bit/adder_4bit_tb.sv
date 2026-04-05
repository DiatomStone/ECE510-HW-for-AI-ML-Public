module adder_4bit_tb;

    // 1. Internal signals to connect to the Design Under Test (DUT)
    logic [3:0] a, b;
    logic       cin;
    logic [3:0] sum;
    logic       cout;

    // 2. Instantiate the module (using .* for implicit port naming)
    adder_4bit dut (.*);

    // 3. Test Stimulus
    initial begin
        // Display header
        $display("Time\t A \t B \t Cin | Sum \t Cout \t Status");
        $display("-----------------------------------------------------");

        // Test Case 1: Simple Addition
        a = 4'd5; b = 4'd2; cin = 0;
        #10 check_result(4'd7, 0);

        // Test Case 2: Max values with Carry
        a = 4'd15; b = 4'd15; cin = 0;
        #10 check_result(4'd14, 1); // 15+15 = 30 (which is 11110 in binary)

        // Test Case 3: Using Carry-In
        a = 4'd10; b = 4'd2; cin = 1;
        #10 check_result(4'd13, 0);

        // Test Case 4: Random loop for stress testing
        repeat (5) begin
            a = 4'($urandom_range(0, 15));
            b = 4'($urandom_range(0, 15));
            cin = 4'($urandom_range(0, 1));
            #10;
            $display("%0t\t %d \t %d \t %b   | %d \t %b", $time, a, b, cin, sum, cout);
        end

        $display("-----------------------------------------------------");
        $display("Simulation complete.");
        $finish;
    end

    // 4. Verification Task
    task check_result(input [3:0] exp_sum, input exp_cout);
        if (sum !== exp_sum || cout !== exp_cout) begin
            $display("%0t\t %d \t %d \t %b   | %d \t %b \t ERROR: Expected %d, Cout %b", 
                     $time, a, b, cin, sum, cout, exp_sum, exp_cout);
        end else begin
            $display("%0t\t %d \t %d \t %b   | %d \t %b \t PASS", 
                     $time, a, b, cin, sum, cout);
        end
    endtask

endmodule
