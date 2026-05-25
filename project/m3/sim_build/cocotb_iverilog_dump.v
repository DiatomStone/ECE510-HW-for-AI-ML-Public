module cocotb_iverilog_dump();
initial begin
    $dumpfile("sim_build/gelu_top.fst");
    $dumpvars(0, gelu_top);
end
endmodule
