module dump_waves;
    initial begin
        $dumpfile("dump.vcd");
        $dumpvars(0, gelu); // Matches your TOPLEVEL name
    end
endmodule
