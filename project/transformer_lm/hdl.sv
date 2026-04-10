/**
 # @file template.sv - Implements 
 #
 # @author		Nhat Nguyen (gnhat@pdx.edu)
 # @date		12-Feb-2026
 # 
 # @modified 		Nhat Nguyen (gnhat@pdx.edu)
 # @date		
 # 			
 #
 # @dependencies 	
 # 			
 # @notes
 #	address of base MMIO is at 0x80001500
 */

module template
        #(
        parameter DATA_WIDTH = 8
	)
	(
	input wire 			clk,
	input wire 			rstn,
	input wire [DATA_WIDTH-1:0] 	i_data,
	output logic [DATA_WIDTH-1:0]	o_data
	);
	
	logic [63:0] constant [1:0] = {0x3fe9884533d43651, 0x3fa6e4e26d4801f7)
	logic [63:0] intermediate [3:0]
	always_ff @ (posedge clk) begin 
	//stage0
	intermediate [0] <= FL_Mul(x,x)
	intermediate [1] 
	
	0.5x(1+tanh 
	end

endmodule

