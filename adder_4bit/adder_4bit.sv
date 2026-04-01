module adder_4bit (
    input  logic [3:0] a,    // 4-bit input A
    input  logic [3:0] b,    // 4-bit input B
    input  logic       cin,  // Carry-in
    output logic [3:0] sum,  // 4-bit Sum output
    output logic       cout  // Carry-out
);

    // Using concatenation {} to capture the 5th bit (carry) 
    // resulting from the 4-bit addition.
    always_comb begin
        {cout, sum} = a + b + {4'b0,cin};
    end

endmodule
