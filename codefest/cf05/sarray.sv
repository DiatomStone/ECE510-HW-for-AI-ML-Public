module sarray
        #(
        parameter N = 12
	)
	(
	input wire 			clk,
	input wire 			rst,	
	input wire [7:0]		weights [N-1:0], //takes one col per cycle	
	input wire [7:0]		activation [N-1:0],	
	output wire [31:0] 		c [N-1:0][N-1:0]
	);
	wire [7:0] a [N:0][N-1:0];	
	wire [7:0] b [N-1:0][N:0];
	logic [7:0] skew_weight [N-1:0];
	logic [7:0] skew_activation [N-1:0];
	genvar i;
	genvar j;
	generate
	for (i = 0; i < N; i = i + 1) begin  : gen_feed
        	assign a[i][0] = skew_activation[i];
        	assign b[0][i] = skew_weight[i];	//we just use i instead and group this together
        end 
        for (i = 0; i < N; i = i + 1) begin  : gen_i
	for (j = 0; j < N; j = j + 1) begin  : gen_j
            mac u_i_j (
            	.clk(clk),
            	.rst(rst),
                .in_a(a[i][j]), 
                .in_b(b[i][j]), 
                .out_a(a[i+1][j]),
                .out_b(b[i][j+1]),
                .out(c[i][j]) //accumulate is held locally in register
            );
        end
        end
    	endgenerate
    	
    	//Skew network should be preskewed to fill sarray
    	always_ff @ (posedge clk) begin
    		if(rst) begin
	    		skew_weight <= '0;
	    		skew_activation <= '0;
    		end else 
    			for ( i = 0; i < 2*N-1; i ++ ) begin // percycle 
    				skew_weight <= 0;
    				skew_activation <= 0;
    			for ( j = 0; j < i+1; j ++ ) begin 
    			if (i < N) begin
    				skew_weight [i-j] <= weight [N-1-j][i-j] //other variables 0
    				skew_activation [i-j] <= activation [i-j][N-1-j]
    			end else begin //i > N
    				skew_weight [i-j-N] <= weight [N-1-j][i-j] //other variables 0
    				skew_activation [i-j-N] <= activation [i-j][N-1-j]
    			end
    			
    			end
    		end
    	end

endmodule

